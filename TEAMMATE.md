# Project 5 - your part

This is the crawler split into two halves. I finished the network half. Your
half is the crawl logic. You only ever call `client.get()` / `client.post()`,
you never touch sockets or TLS.

## What I already did

`http_client.py` - the whole HTTP/1.1 over TLS layer. It's done and tested
against a real HTTPS server.

- TLS socket, keep-alive connection, reconnects if the server drops it
- Builds HTTP/1.1 requests (Host header, etc.) and parses the responses
- Handles chunked transfer-encoding and gzip for you
- Cookie jar: reads `Set-Cookie` and sends the `Cookie` header automatically,
  so you don't manage cookies at all
- Retries 503 on its own

You get this API:

```python
client.get(path, extra_headers=None)    # -> HTTPResponse
client.post(path, form_fields, ...)      # form_fields is a dict
client.get_cookie(name)                  # -> str or None
```

`HTTPResponse` has: `.status` (int), `.reason` (str), `.headers` (dict, keys
are lowercase), `.body` (str, already decoded).

I also set up `4700crawler` (the skeleton, argument parsing, the run loop) and
the `Makefile`.

## What you need to do

All of it is in `4700crawler`, the four methods marked `TODO`. They currently
just `raise NotImplementedError`.

### 1. `login()`

Fakebook uses a Django login form with CSRF protection.

1. `client.get(LOGIN_PATH)` first. The client picks up the `csrftoken` cookie
   automatically - read it with `client.get_cookie('csrftoken')`.
2. Parse the returned HTML for the hidden input named `csrfmiddlewaretoken`.
3. `client.post(LOGIN_PATH, {...})` with `username`, `password`,
   `csrfmiddlewaretoken`, and `next=/fakebook/`. The client sends the cookie
   and saves the `sessionid` it gets back.
4. A successful login returns a 302. Follow it.

The catch: the CSRF token is in both a cookie and a hidden form field, and you
need both.

### 2. `extract_links(html)`

Use `html.parser` (allowed). Pull every `<a href>`, keep only links that point
at this server and are under `/fakebook/`. Drop external domains. Return a list
of paths.

### 3. `extract_flags(html)`

Find the flags, which look like:

```html
<h3 class='secret_flag' style="color:red">FLAG: 64-chars-here</h3>
```

Return the 64-char strings, without the `FLAG: ` prefix.

### 4. `crawl()`

The main loop. Pull a path off `self.frontier`, GET it, and:

- 200: run `extract_flags` and `extract_links`, add new links to the frontier
- 302: requeue the path from the `Location` header
- 403 / 404: drop the path
- (503 is already retried inside the client, you won't see it)

Track visited paths in `self.visited` so you don't loop forever - friends link
to each other, so A->B->A will spin if you don't. Stop once `self.flags` has 5.

## Rules to stay legal

Allowed: `socket`, `ssl`, `urllib.parse`, `html`, `html.parser`, `xml`.
Not allowed: `requests`, `urllib`/`urllib2`, `httplib`, `pycurl`,
`beautifulsoup`, `cookielib`, `lxml`, or anything that does HTTP/cookies for you.

So use `html.parser` for parsing, not BeautifulSoup. Don't import anything that
talks HTTP - that's what `http_client.py` is for.

## Run it

```bash
make
./4700crawler <username> <password>
```

It should print exactly the 5 flags, one per line, and nothing else.

## Still left after your part (we'll do together)

- `README.md` for submission (approach, challenges, testing)
- `secret_flags` file - 10 lines, both our flags
- A real run against Fakebook with our Northeastern logins
