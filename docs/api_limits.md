# API rate limits

The standard API rate limit is 100 requests per minute per workspace. The response includes rate-limit headers showing the current limit and remaining requests.

When a workspace exceeds its rate limit, the API returns HTTP 429 Too Many Requests. The response includes a `Retry-After` header indicating how many seconds to wait before retrying. Clients should wait for that interval before sending another request.
