# CS 5700 Project 5 - Web Crawler

A web crawler that logs in to Fakebook and traverses the site looking for five secret flags. `4700crawler` handles the login, the crawl, and parsing pages for links and flags. `http_client.py` is the HTTP/1.1 over TLS layer that every request goes through. All HTTP framing, parsing, and cookie handling is written from scratch; no HTTP or cookie libraries are used.

## Files

- `4700crawler` - the crawler. Logs in, walks the frontier, prints the flags.
- `http_client.py` - HTTP/1.1 client over TLS: requests, response parsing,
chunked and gzip decoding, cookies, and a 503 retry.
- `Makefile` - runs `chmod +x` on `4700crawler`.
- `secret_flags` - the flags for both group members.
- `README.md` - this file.

## Build and run

```bash
make
./4700crawler <username> <password>
```

The `-s` and `-p` flags override the server and port:

```bash
./4700crawler -s server.example.com -p 443 <username> <password>
```

The crawler prints exactly five lines to stdout, one flag per line. Errors, if any, go to stderr.

## Approach

### HTTP layer (`http_client.py`)

`HTTPClient` wraps a single TCP socket in TLS and keeps it alive across requests, reconnecting if the server closes the connection. `get` and `post` build the request, send it, and return an `HTTPResponse` with the status, headers (lowercased keys), and decoded body.

- Responses are read off a small buffered reader so we can grab header lines and exact byte counts without reading into the next response.
- The body is read by `Content-Length` or by reassembling a chunked response, and then gzip/deflate decoded if the server compressed it.
- Cookies are managed here: every `Set-Cookie` is stored in a jar and sent back as a `Cookie` header on later requests, so the crawler never touches them.
- A 503 is retried automatically; all other status codes are returned to the caller to handle.

### Crawler (`4700crawler`)

The crawler logs in, then runs a frontier-based crawl from `/fakebook/`.

- Login GETs the login page to pick up the `csrftoken` cookie and the hidden `csrfmiddlewaretoken` form field, then POSTs the credentials with both. A `Referer` header is sent because Django's CSRF check rejects the POST without it. The 302 that follows a successful login is followed to confirm the session.
- HTML is parsed with `html.parser`. One parser pulls `<a href>` links, another pulls the text of `<h3 class='secret_flag'>` tags and strips the `FLAG:` prefix.
- Links are normalized to same-server paths under `/fakebook/`; external domains and other paths are dropped.
- The frontier is a stack and `visited` is a set, so pages are not crawled twice and friend links that point back and forth do not loop.
- During the crawl, 200 pages are parsed for flags and links, 302 redirects are requeued, and 403/404 pages are dropped. The crawl stops as soon as five flags are found.

## Challenges

**CSRF login.** The login form was not just username and password. Django protects the form with a CSRF token that appears both as a cookie and as a hidden input, and the POST also needs a `Referer` header to pass the HTTPS CSRF check. Logging in only worked once all three were handled together.

**Chunked and compressed responses.** The server returns chunked responses and can gzip them, so the body could not be read by length alone. The client reassembles the chunks first, then decompresses, before handing back text.

**Avoiding loops.** Friends link to each other, so without a visited set the crawler ping-pongs between two profiles forever. Tracking visited paths and skipping them keeps the crawl finite.

## Testing

We tested the HTTP layer on its own against a live HTTPS server to confirm the TLS handshake, header parsing, chunked reassembly, gzip decoding, cookie storage, and keep-alive reuse all worked. We then ran `4700crawler` end to end against Fakebook with our own credentials and confirmed it logged in and printed five flags. We also checked that it handles 302 redirects, skips 403/404 pages, and stays on the target domain.