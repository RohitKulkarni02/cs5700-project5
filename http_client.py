#!/usr/bin/env python3

import gzip
import socket
import ssl
from urllib.parse import urlencode


MAX_503_RETRIES = 50
RECV_SIZE = 65536


# parsed response: status, reason, headers dict, decoded body
class HTTPResponse:
    def __init__(self, status, reason, headers, body):
        self.status = status
        self.reason = reason
        self.headers = headers
        self.body = body


# buffered reader so we can pull whole lines or exact byte counts
class SocketReader:
    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def _fill(self):
        chunk = self.sock.recv(RECV_SIZE)
        if not chunk:
            raise ConnectionError("server closed the connection")
        self.buf += chunk

    def read_line(self):
        while b"\r\n" not in self.buf:
            self._fill()
        line, self.buf = self.buf.split(b"\r\n", 1)
        return line

    def read_exactly(self, n):
        while len(self.buf) < n:
            self._fill()
        data, self.buf = self.buf[:n], self.buf[n:]
        return data


# http/1.1 over one keep-alive tls connection, with its own cookie jar
class HTTPClient:
    def __init__(self, host, port, use_tls=True):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.sock = None
        self.reader = None
        self.cookies = {}

    def connect(self):
        raw = socket.create_connection((self.host, self.port))
        if self.use_tls:
            context = ssl.create_default_context()
            raw = context.wrap_socket(raw, server_hostname=self.host)
        self.sock = raw
        self.reader = SocketReader(raw)

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None
                self.reader = None

    def _ensure_connection(self):
        if self.sock is None:
            self.connect()

    def get_cookie(self, name):
        return self.cookies.get(name)

    def _store_cookies(self, headers_list):
        # raw list, not the dict, since there can be multiple Set-Cookie headers
        for name, value in headers_list:
            if name.lower() != "set-cookie":
                continue
            cookie = value.split(";", 1)[0].strip()
            if "=" in cookie:
                cname, cval = cookie.split("=", 1)
                self.cookies[cname.strip()] = cval.strip()

    def _cookie_header(self):
        if not self.cookies:
            return None
        return "; ".join("%s=%s" % (k, v) for k, v in self.cookies.items())

    def get(self, path, extra_headers=None):
        return self._request_with_retry("GET", path, None, extra_headers)

    def post(self, path, form_fields, extra_headers=None):
        # post a dict as form-urlencoded
        body = urlencode(form_fields).encode("ascii")
        headers = dict(extra_headers or {})
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return self._request_with_retry("POST", path, body, headers)

    def _request_with_retry(self, method, path, body, extra_headers):
        # retry 503, return everything else to the caller
        attempts = 0
        while True:
            response = self._request_once(method, path, body, extra_headers)
            if response.status == 503 and attempts < MAX_503_RETRIES:
                attempts += 1
                continue
            return response

    def _request_once(self, method, path, body, extra_headers):
        # retry once if the keep-alive connection was dropped
        for attempt in range(2):
            self._ensure_connection()
            try:
                self._send_request(method, path, body, extra_headers)
                return self._read_response()
            except (ConnectionError, ssl.SSLError, socket.error):
                self.close()
                if attempt == 1:
                    raise

    def _send_request(self, method, path, body, extra_headers):
        lines = ["%s %s HTTP/1.1" % (method, path)]
        headers = {
            "Host": self.host,
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip",
            "Accept": "*/*",
        }
        if body is not None:
            headers["Content-Length"] = str(len(body))
        cookie = self._cookie_header()
        if cookie:
            headers["Cookie"] = cookie
        if extra_headers:
            headers.update(extra_headers)

        for name, value in headers.items():
            lines.append("%s: %s" % (name, value))
        raw = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")
        if body is not None:
            raw += body
        self.sock.sendall(raw)

    def _read_response(self):
        status, reason = self._read_status_line()
        headers_list = self._read_headers()
        self._store_cookies(headers_list)

        # lowercase the header keys
        headers = {}
        for name, value in headers_list:
            headers[name.lower()] = value

        raw_body = self._read_body(headers)
        body = self._decode_body(headers, raw_body)

        if headers.get("connection", "").lower() == "close":
            self.close()

        return HTTPResponse(status, reason, headers, body)

    def _read_status_line(self):
        # "HTTP/1.1 200 OK"
        line = self.reader.read_line().decode("iso-8859-1")
        parts = line.split(" ", 2)
        if len(parts) < 2:
            raise ConnectionError("malformed status line: %r" % line)
        status = int(parts[1])
        reason = parts[2] if len(parts) > 2 else ""
        return status, reason

    def _read_headers(self):
        headers = []
        while True:
            line = self.reader.read_line().decode("iso-8859-1")
            if line == "":
                break
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers.append((name.strip(), value.strip()))
        return headers

    def _read_body(self, headers):
        if headers.get("transfer-encoding", "").lower() == "chunked":
            return self._read_chunked()
        if "content-length" in headers:
            return self.reader.read_exactly(int(headers["content-length"]))
        return b""

    def _read_chunked(self):
        body = b""
        while True:
            size_line = self.reader.read_line().decode("iso-8859-1")
            size = int(size_line.split(";", 1)[0].strip(), 16)
            if size == 0:
                while self.reader.read_line() != b"":
                    pass
                break
            body += self.reader.read_exactly(size)
            self.reader.read_exactly(2)
        return body

    def _decode_body(self, headers, raw_body):
        if raw_body and headers.get("content-encoding", "").lower() == "gzip":
            raw_body = gzip.decompress(raw_body)
        return raw_body.decode("utf-8", errors="replace")