# Authentication

The Example Developer Platform API supports API keys and OAuth 2.0 client credentials. Supported authentication methods are API keys and OAuth 2.0 client credentials. Send an API key in the `Authorization: Bearer` header. For OAuth 2.0, exchange a client ID and client secret for a short-lived access token, then send that token as a bearer token.

Create and revoke API keys from the workspace security settings. Treat API keys and client secrets as confidential credentials; do not place them in browser code or public repositories. Requests without valid credentials receive an HTTP 401 response.
