function jsonError(detail, status) {
  return Response.json(
    { detail },
    {
      status,
      headers: {
        'Cache-Control': 'no-store',
      },
    },
  )
}

export async function onRequest(context) {
  const configuredBackend = context.env.BACKEND_URL?.trim()

  if (!configuredBackend) {
    return jsonError(
      'Backend is not configured. Set BACKEND_URL in Cloudflare Pages → Settings → Variables and Secrets.',
      503,
    )
  }

  const backendRoot = configuredBackend.replace(/\/+$/, '')
  const backendApi = backendRoot.endsWith('/api') ? backendRoot : `${backendRoot}/api`

  const rawPath = context.params.path
  const pathParts = Array.isArray(rawPath)
    ? rawPath.map(String)
    : rawPath === undefined
      ? []
      : [String(rawPath)]

  const incomingUrl = new URL(context.request.url)
  const encodedPath = pathParts.map((part) => encodeURIComponent(part)).join('/')
  const targetUrl = new URL(encodedPath ? `${backendApi}/${encodedPath}` : backendApi)
  targetUrl.search = incomingUrl.search

  const headers = new Headers(context.request.headers)
  headers.delete('host')

  try {
    const method = context.request.method
    const body = method === 'GET' || method === 'HEAD' ? undefined : await context.request.arrayBuffer()

    const upstream = await fetch(targetUrl.toString(), {
      method,
      headers,
      body,
      redirect: 'manual',
    })

    const responseHeaders = new Headers(upstream.headers)
    responseHeaders.set('Cache-Control', 'no-store')

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    })
  } catch (error) {
    console.error('Future Oracle API proxy error', error)
    return jsonError('Backend is unavailable. Check BACKEND_URL and the FastAPI deployment.', 502)
  }
}
