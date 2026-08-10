import { createServer } from 'node:http'
import next from 'next'

// Test-only custom server. The documented `next()` API keeps the dev server in
// this process, whereas the Next CLI always forks a second Node process before
// it starts listening. Some hermetic CI/sandbox environments forbid that fork.
const hostname = process.env.ROBOT_FRONTEND_HOST ?? '127.0.0.1'
const rawPort = process.env.ROBOT_FRONTEND_PORT ?? '3100'

if (!/^\d+$/.test(rawPort)) {
  throw new Error(`ROBOT_FRONTEND_PORT doit être un entier, reçu : ${rawPort}`)
}

const port = Number(rawPort)
if (!Number.isSafeInteger(port) || port < 1 || port > 65_535) {
  throw new Error(`ROBOT_FRONTEND_PORT doit être compris entre 1 et 65535, reçu : ${rawPort}`)
}

const app = next({
  dev: true,
  dir: process.cwd(),
  hostname,
  port,
  turbopack: true,
})
const handle = app.getRequestHandler()

await app.prepare()

const server = createServer((request, response) => {
  void handle(request, response).catch((error) => {
    console.error('[robot-server] Requête Next.js en échec.', error)
    if (!response.headersSent) response.statusCode = 500
    if (!response.writableEnded) response.end('Internal Server Error')
  })
})

await new Promise((resolve, reject) => {
  server.once('error', reject)
  server.listen(port, hostname, resolve)
})

console.log(`[robot-server] Prêt sur http://${hostname}:${port}`)

let shutdownStarted = false
async function shutdown(signal) {
  if (shutdownStarted) return
  shutdownStarted = true
  console.log(`[robot-server] Arrêt demandé (${signal}).`)

  await new Promise((resolve) => {
    server.close(() => resolve())
    server.closeAllConnections?.()
  })
  await app.close()
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => {
    void shutdown(signal)
      .catch((error) => {
        console.error('[robot-server] Arrêt incomplet.', error)
        process.exitCode = 1
      })
      .finally(() => process.exit())
  })
}
