#!/usr/bin/env python3
"""Thư viện giao tiếp IPC với greetd (theo chuẩn greetd-ipc(7)).

Cung cấp:
- GreetdError: Ngoại lệ giao thức greetd.
- GreetdClient: Client kết nối Unix socket với greetd để tạo phiên, xác thực và khởi chạy WM.
- MockGreetd: Máy chủ greetd giả lập chạy trên luồng nền phục vụ kiểm thử.
- list_users: Đọc danh sách người dùng thực từ /etc/passwd.
- list_sessions: Quét các phiên đăng nhập Wayland từ file .desktop.
- selftest: Bộ kiểm thử tự động toàn diện.
"""

from __future__ import annotations

import configparser
import json
import os
import shlex
import shutil
import socket
import struct
import sys
import tempfile
import threading
from typing import Any, Callable, Iterable

# Định dạng header: 4 byte uint32 theo thứ tự byte native của hệ thống
_HEADER_STRUCT = struct.Struct("=I")
_MAX_MSG_SIZE = 1024 * 1024  # Giới hạn an toàn 1 MiB cho mỗi gói JSON


class GreetdError(Exception):
    """Ngoại lệ phát sinh khi greetd trả về lỗi hoặc kết nối IPC gặp sự cố."""

    def __init__(self, error_type: str, description: str) -> None:
        super().__init__(f"{error_type}: {description}")
        self.error_type = error_type
        self.description = description


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Đọc chính xác n byte từ socket, phát sinh EOFError nếu kết nối đóng sớm."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("Kết nối socket đã đóng trước khi nhận đủ dữ liệu")
        buf.extend(chunk)
    return bytes(buf)


def _write_packet(sock: socket.socket, payload: dict[str, Any]) -> None:
    """Đóng gói dict thành JSON UTF-8 kèm 4 byte độ dài và gửi qua socket."""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = _HEADER_STRUCT.pack(len(raw))
    sock.sendall(header + raw)


def _read_packet(sock: socket.socket) -> dict[str, Any]:
    """Đọc 4 byte độ dài và giải mã gói JSON UTF-8 từ socket."""
    header = _recv_exact(sock, _HEADER_STRUCT.size)
    (length,) = _HEADER_STRUCT.unpack(header)
    if length > _MAX_MSG_SIZE:
        raise ValueError(f"Kích thước gói tin quá lớn: {length} byte")
    body = _recv_exact(sock, length)
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Phản hồi JSON từ greetd không phải là object")
    return data


class GreetdClient:
    """Client giao tiếp với daemon greetd qua Unix domain socket."""

    def __init__(self, sock_path: str | None = None) -> None:
        if sock_path is None:
            sock_path = os.environ.get("GREETD_SOCK", "")
        if not sock_path:
            raise GreetdError("error", "Không tìm thấy đường dẫn GREETD_SOCK")
        self.sock_path = sock_path
        self._sock: socket.socket | None = None
        self._connect()

    def _connect(self) -> None:
        """Mở kết nối tới Unix socket của greetd với timeout 30 giây."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(30.0)
            sock.connect(self.sock_path)
            self._sock = sock
        except OSError as exc:
            raise GreetdError("error", f"Không thể kết nối tới greetd socket: {exc}") from exc

    def _send(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Gửi 1 yêu cầu JSON và đọc đúng 1 phản hồi từ greetd."""
        if self._sock is None:
            raise GreetdError("error", "Kết nối socket đã bị đóng")
        try:
            _write_packet(self._sock, obj)
            return _read_packet(self._sock)
        except (OSError, EOFError, ValueError, json.JSONDecodeError) as exc:
            raise GreetdError("error", f"Lỗi truyền thông IPC với greetd: {exc}") from exc

    def close(self) -> None:
        """Đóng kết nối socket hiện tại."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            finally:
                self._sock = None

    def __enter__(self) -> GreetdClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # --- Các hàm giao tiếp cấp thấp ---

    def create_session(self, username: str) -> dict[str, Any]:
        """Bắt đầu phiên xác thực cho người dùng."""
        return self._send({"type": "create_session", "username": username})

    def post_response(self, response: str | None = None) -> dict[str, Any]:
        """Trả lời thông điệp xác thực (auth_message) từ greetd/PAM."""
        return self._send({
            "type": "post_auth_message_response",
            "response": response,
        })

    def start_session(
        self,
        cmd: list[str],
        env: list[str] | None = None,
    ) -> dict[str, Any]:
        """Yêu cầu greetd khởi chạy phiên làm việc sau khi đã xác thực thành công."""
        return self._send({
            "type": "start_session",
            "cmd": list(cmd),
            "env": list(env) if env is not None else [],
        })

    def cancel_session(self) -> dict[str, Any]:
        """Huỷ phiên đang mở hoặc đang xác thực dở dang."""
        return self._send({"type": "cancel_session"})

    # --- Hàm đăng nhập cấp cao ---

    def login(
        self,
        username: str,
        password: str,
        cmd: list[str],
        env: list[str] | None = None,
        on_info: Callable[[str, str], None] | None = None,
    ) -> None:
        """Thực hiện trọn vẹn quy trình đăng nhập và khởi chạy lệnh phiên.

        - Tự động trả lời các bước PAM (secret -> mật khẩu 1 lần, visible -> username,
          info/error -> gọi callback on_info rồi gửi response None).
        - Nếu gặp lỗi từ greetd, tự động gửi cancel_session để dọn trạng thái rồi
          phát sinh GreetdError.
        - Giới hạn tối đa 10 vòng lặp xác thực để tránh treo vô tận.
        """
        pw_holder: list[str | None] = [password]
        del password  # Không giữ tham chiếu trực tiếp để hạn chế rò rỉ

        def _consume_password() -> str:
            pw = pw_holder[0]
            pw_holder[0] = None
            return pw if pw is not None else ""

        def _cancel_quietly() -> None:
            try:
                self.cancel_session()
            except Exception:
                pass

        resp = self.create_session(username)

        for _ in range(10):
            rtype = resp.get("type")

            if rtype == "auth_message":
                msg_type = resp.get("auth_message_type", "")
                msg_text = resp.get("auth_message", "")
                if msg_type == "secret":
                    resp = self.post_response(_consume_password())
                elif msg_type == "visible":
                    resp = self.post_response(username or "")
                elif msg_type in ("info", "error"):
                    if on_info is not None:
                        on_info(msg_type, msg_text)
                    resp = self.post_response(None)
                else:
                    _cancel_quietly()
                    raise GreetdError("error", f"Loại auth_message không hỗ trợ: {msg_type}")

            elif rtype == "success":
                start_resp = self.start_session(cmd, env)
                st_type = start_resp.get("type")
                if st_type == "success":
                    return
                if st_type == "error":
                    _cancel_quietly()
                    raise GreetdError(
                        start_resp.get("error_type", "error"),
                        start_resp.get("description", "Không thể khởi chạy phiên"),
                    )
                _cancel_quietly()
                raise GreetdError("error", f"Phản hồi start_session bất thường: {st_type}")

            elif rtype == "error":
                err_type = resp.get("error_type", "error")
                desc = resp.get("description", "Lỗi không xác định từ greetd")
                _cancel_quietly()
                raise GreetdError(err_type, desc)

            else:
                _cancel_quietly()
                raise GreetdError("error", f"Phản hồi không hợp lệ từ greetd: {rtype}")

        _cancel_quietly()
        raise GreetdError("error", "Quá số vòng xác thực tối đa (10 vòng)")


class MockGreetd:
    """Máy chủ greetd giả lập chạy trên luồng nền phục vụ kiểm thử giao thức."""

    def __init__(
        self,
        users: dict[str, str] | None = None,
        sock_path: str | None = None,
    ) -> None:
        self.users: dict[str, str] = dict(users) if users is not None else {"demo": "pass"}
        if sock_path is None:
            self._temp_dir: str | None = tempfile.mkdtemp(prefix="mock_greetd_")
            self.sock_path = os.path.join(self._temp_dir, "greetd.sock")
        else:
            self._temp_dir = None
            self.sock_path = sock_path

        self.started: tuple[str, list[str], list[str]] | None = None
        self._server_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    def start(self) -> str:
        """Khởi động socket server trong luồng nền và trả về đường dẫn socket."""
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.sock_path)
        srv.listen(8)
        srv.settimeout(0.2)
        self._server_sock = srv
        self._running.set()

        self._thread = threading.Thread(target=self._serve_loop, name="MockGreetdThread", daemon=True)
        self._thread.start()
        return self.sock_path

    def stop(self) -> None:
        """Dừng luồng server, đóng và xoá file socket tạm."""
        self._running.clear()
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

        if self._temp_dir is not None and os.path.isdir(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def _serve_loop(self) -> None:
        """Vòng lặp chấp nhận các kết nối nối tiếp nhau."""
        while self._running.is_set() and self._server_sock is not None:
            try:
                conn, _ = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with conn:
                conn.settimeout(5.0)
                self._handle_client(conn)

    def _handle_client(self, conn: socket.socket) -> None:
        """Xử lý tuần tự nhiều request trên cùng một kết nối client."""
        current_user: str | None = None
        authenticated = False
        awaiting_password = False

        while self._running.is_set():
            try:
                req = _read_packet(conn)
            except (EOFError, OSError, ValueError, json.JSONDecodeError):
                break

            rtype = req.get("type")

            if rtype == "create_session":
                username = req.get("username")
                if not isinstance(username, str) or not username:
                    _write_packet(conn, {
                        "type": "error",
                        "error_type": "error",
                        "description": "Missing username",
                    })
                    continue
                current_user = username
                authenticated = False
                awaiting_password = True
                # Luôn hỏi mật khẩu kể cả khi user không tồn tại (giống hành vi PAM)
                _write_packet(conn, {
                    "type": "auth_message",
                    "auth_message_type": "secret",
                    "auth_message": "Password:",
                })

            elif rtype == "post_auth_message_response":
                if not awaiting_password or current_user is None:
                    _write_packet(conn, {
                        "type": "error",
                        "error_type": "error",
                        "description": "No active authentication prompt",
                    })
                    continue

                response = req.get("response")
                awaiting_password = False
                expected_pw = self.users.get(current_user)
                if expected_pw is not None and response == expected_pw:
                    authenticated = True
                    _write_packet(conn, {"type": "success"})
                else:
                    authenticated = False
                    _write_packet(conn, {
                        "type": "error",
                        "error_type": "auth_error",
                        "description": "Authentication failed",
                    })

            elif rtype == "start_session":
                if not authenticated or current_user is None:
                    _write_packet(conn, {
                        "type": "error",
                        "error_type": "error",
                        "description": "Session not authenticated",
                    })
                    continue
                cmd = [str(x) for x in req.get("cmd", [])]
                env = [str(x) for x in req.get("env", [])]
                self.started = (current_user, cmd, env)
                _write_packet(conn, {"type": "success"})

            elif rtype == "cancel_session":
                current_user = None
                authenticated = False
                awaiting_password = False
                _write_packet(conn, {"type": "success"})

            else:
                _write_packet(conn, {
                    "type": "error",
                    "error_type": "error",
                    "description": f"Unknown request type: {rtype}",
                })


def list_users(passwd: str = "/etc/passwd") -> list[dict[str, Any]]:
    """Đọc danh sách người dùng thường từ file passwd.

    Chỉ lấy các tài khoản có UID trong đoạn 1000..59999 và shell không chứa
    'nologin' hoặc 'false'. Sắp xếp tăng dần theo UID.
    """
    users: list[dict[str, Any]] = []
    try:
        with open(passwd, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) < 7:
                    continue
                name, _, uid_str, _, gecos, home, shell = parts[:7]
                try:
                    uid = int(uid_str)
                except ValueError:
                    continue
                if not (1000 <= uid <= 59999):
                    continue
                shell_lower = shell.lower()
                if "nologin" in shell_lower or "false" in shell_lower:
                    continue
                display_gecos = gecos.split(",")[0].strip() if gecos else ""
                users.append({
                    "name": name,
                    "uid": uid,
                    "gecos": display_gecos,
                    "home": home,
                })
    except OSError:
        return []

    users.sort(key=lambda u: u["uid"])
    return users


def list_sessions(
    dirs: Iterable[str] = ("/usr/share/wayland-sessions",),
) -> list[dict[str, Any]]:
    """Quét danh sách các phiên đăng nhập từ các thư mục chứa file .desktop.

    - Dùng configparser (interpolation=None, strict=False) đọc mục [Desktop Entry].
    - Bỏ qua các file có Hidden=true, NoDisplay=true hoặc thiếu Name/Exec/lỗi cú pháp.
    - Tách Exec bằng shlex.split và loại bỏ các mã trường (%f, %F, %u, %U, ...).
    - Ưu tiên phiên có Exec chứa 'start-hyprland' lên đầu, sau đó sắp theo tên.
    """
    sessions: list[dict[str, Any]] = []

    for d in dirs:
        if not os.path.isdir(d):
            continue
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            continue

        for fname in entries:
            if not fname.endswith(".desktop"):
                continue
            fpath = os.path.join(d, fname)
            if not os.path.isfile(fpath):
                continue

            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    cp.read_file(f)
            except (OSError, configparser.Error):
                continue

            if not cp.has_section("Desktop Entry"):
                continue

            section = cp["Desktop Entry"]
            if section.get("Hidden", "").strip().lower() == "true":
                continue
            if section.get("NoDisplay", "").strip().lower() == "true":
                continue

            name = section.get("Name", "").strip()
            exec_raw = section.get("Exec", "").strip()
            if not name or not exec_raw:
                continue

            try:
                tokens = shlex.split(exec_raw)
            except ValueError:
                continue

            # Loại bỏ các mã %f, %u, %F, %U, %i, %c, %k... theo chuẩn Desktop Entry
            cmd = [tok for tok in tokens if not (tok.startswith("%") and len(tok) == 2)]
            if not cmd:
                continue

            sessions.append({
                "name": name,
                "exec": cmd,
                "file": fpath,
            })

    def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
        has_hypr = any("start-hyprland" in part for part in item["exec"])
        return (0 if has_hypr else 1, item["name"].lower())

    sessions.sort(key=_sort_key)
    return sessions


def selftest() -> int:
    """Chạy bộ kiểm thử tự động cho toàn bộ module. Trả về 0 nếu tất cả PASS."""
    passed = 0
    failed = 0

    def _record(ok: bool, label: str, detail: str = "") -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS: {label}")
        else:
            failed += 1
            msg = f"FAIL: {label}" + (f" ({detail})" if detail else "")
            print(msg)

    mock = MockGreetd(users={"kafka": "stellaron"})
    sock_path = mock.start()
    try:
        # 1. Đăng nhập đúng thông tin
        try:
            with GreetdClient(sock_path) as client:
                client.login(
                    "kafka",
                    "stellaron",
                    ["start-hyprland"],
                    ["XDG_SESSION_TYPE=wayland"],
                )
            ok = mock.started == (
                "kafka",
                ["start-hyprland"],
                ["XDG_SESSION_TYPE=wayland"],
            )
            _record(ok, "Mock + Client đăng nhập đúng & kiểm tra mock.started")
        except Exception as exc:
            _record(False, "Mock + Client đăng nhập đúng & kiểm tra mock.started", str(exc))

        # 2. Sai mật khẩu -> raise GreetdError(auth_error)
        try:
            with GreetdClient(sock_path) as client:
                client.login("kafka", "wrongpass", ["start-hyprland"])
            _record(False, "Sai mật khẩu phải raise GreetdError auth_error", "Không raise lỗi")
        except GreetdError as exc:
            _record(
                exc.error_type == "auth_error",
                "Sai mật khẩu raise GreetdError auth_error",
                f"error_type={exc.error_type}",
            )
        except Exception as exc:
            _record(False, "Sai mật khẩu raise GreetdError auth_error", str(exc))

        # 3. User lạ -> vẫn hỏi password rồi trả auth_error
        try:
            with GreetdClient(sock_path) as client:
                client.login("blade", "anything", ["start-hyprland"])
            _record(False, "User lạ phải raise GreetdError auth_error", "Không raise lỗi")
        except GreetdError as exc:
            _record(
                exc.error_type == "auth_error",
                "User lạ raise GreetdError auth_error",
                f"error_type={exc.error_type}",
            )
        except Exception as exc:
            _record(False, "User lạ raise GreetdError auth_error", str(exc))

        # 4. Đăng nhập lại thành công trên kết nối mới sau các lần thất bại
        mock.started = None
        try:
            with GreetdClient(sock_path) as client:
                client.login("kafka", "stellaron", ["Hyprland"], ["LANG=vi_VN.UTF-8"])
            ok = mock.started == ("kafka", ["Hyprland"], ["LANG=vi_VN.UTF-8"])
            _record(ok, "Đăng nhập lại thành công sau khi sai trên kết nối mới")
        except Exception as exc:
            _record(False, "Đăng nhập lại thành công sau khi sai trên kết nối mới", str(exc))
    finally:
        mock.stop()

    # 5. Kiểm thử list_users với file passwd tạm
    tmp_dir = tempfile.mkdtemp(prefix="greetd_test_")
    try:
        passwd_file = os.path.join(tmp_dir, "passwd")
        with open(passwd_file, "w", encoding="utf-8") as f:
            f.write(
                "root:x:0:0:Super User:/root:/bin/bash\n"
                "nobody:x:65534:65534:Kernel Overflow User:/:/usr/bin/nologin\n"
                "daemon:x:1001:1001:Service Account:/var/empty:/sbin/nologin\n"
                "locked:x:1002:1002:Locked User:/home/locked:/bin/false\n"
                "silverwolf:x:1005:1005:Silver Wolf,Herta:/home/silverwolf:/bin/zsh\n"
                "kafka:x:1000:1000:Kafka Hunter:/home/kafka:/bin/bash\n"
            )
        users = list_users(passwd_file)
        expected_names = [u["name"] for u in users]
        ok = (
            expected_names == ["kafka", "silverwolf"]
            and users[0]["uid"] == 1000
            and users[1]["gecos"] == "Silver Wolf"
        )
        _record(ok, "list_users lọc đúng UID 1000..59999, bỏ nologin/false và sắp theo UID")

        # 6. Kiểm thử list_sessions với thư mục .desktop tạm
        sess_dir = os.path.join(tmp_dir, "sessions")
        os.makedirs(sess_dir, exist_ok=True)

        # File 1: Exec có %U
        with open(os.path.join(sess_dir, "sway.desktop"), "w", encoding="utf-8") as f:
            f.write(
                "[Desktop Entry]\n"
                "Name=Sway\n"
                "Exec=sway --config /etc/sway/config %U\n"
                "Type=Application\n"
            )

        # File 2: start-hyprland (phải được ưu tiên xếp đầu)
        with open(os.path.join(sess_dir, "hyprland.desktop"), "w", encoding="utf-8") as f:
            f.write(
                "[Desktop Entry]\n"
                "Name=Hyprland (Kafka)\n"
                "Exec=/usr/bin/start-hyprland %f\n"
                "Type=Application\n"
            )

        # File 3: Hidden=true (phải bị bỏ qua)
        with open(os.path.join(sess_dir, "hidden.desktop"), "w", encoding="utf-8") as f:
            f.write(
                "[Desktop Entry]\n"
                "Name=Hidden WM\n"
                "Exec=hidden-wm\n"
                "Hidden=true\n"
            )

        # File 4: File hỏng cú pháp / không có [Desktop Entry]
        with open(os.path.join(sess_dir, "broken.desktop"), "w", encoding="utf-8") as f:
            f.write("@@@ Đây không phải file INI hợp lệ @@@\nExec=\n")

        sessions = list_sessions((sess_dir,))
        ok = (
            len(sessions) == 2
            and sessions[0]["name"] == "Hyprland (Kafka)"
            and sessions[0]["exec"] == ["/usr/bin/start-hyprland"]
            and sessions[1]["name"] == "Sway"
            and sessions[1]["exec"] == ["sway", "--config", "/etc/sway/config"]
        )
        _record(
            ok,
            "list_sessions ưu tiên start-hyprland, bỏ Hidden=true, bỏ file hỏng và lọc %U/%f",
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = passed + failed
    print(f"\nTổng kết selftest: {passed}/{total} PASS, {failed} FAIL.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    elif "--list" in sys.argv[1:]:
        output = {
            "users": list_users(),
            "sessions": list_sessions(),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("Cách dùng: python3 greetd_ipc.py [--selftest | --list]")
