# Webhooks

Webhook deliveries use HTTPS POST requests with a JSON event body. Each delivery includes a signature header that consumers can verify with the signing secret configured for the endpoint.

Failed webhook deliveries are retried with exponential backoff for up to 24 hours. Delivery logs are retained for 14 days and can be viewed in the workspace dashboard. The platform does not guarantee delivery after the retry period expires.