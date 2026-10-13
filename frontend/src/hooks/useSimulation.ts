import { useEffect } from 'react'
import { useWorld } from '../stores/world'
import type { Snapshot } from '../types/world'
export function useSimulation() {
  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout>
    let closed = false
    let attempts = 0
    let lastReply = Date.now()
    const connect = () => {
      if (closed || !navigator.onLine) return
      const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/simulation`)
      socket = ws
      ws.onopen = () => { attempts = 0; lastReply = Date.now(); useWorld.setState({ connection: 'live', error: null }) }
      ws.onmessage = event => {
        lastReply = Date.now()
        try { useWorld.getState().accept(JSON.parse(event.data) as Snapshot) }
        catch { useWorld.setState({ error: 'Invalid state update received' }) }
      }
      ws.onclose = () => {
        if (closed) return
        useWorld.setState({ connection: 'reconnecting' })
        clearTimeout(timer)
        timer = setTimeout(connect, Math.min(5000, 800 * 2 ** attempts++))
      }
      ws.onerror = () => ws.close()
    }
    const offline = () => { clearTimeout(timer); socket?.close(); useWorld.setState({ connection: 'reconnecting' }) }
    const online = () => { clearTimeout(timer); if (!socket || socket.readyState >= WebSocket.CLOSING) connect() }
    window.addEventListener('offline', offline)
    window.addEventListener('online', online)
    const heartbeat = setInterval(() => {
      if (socket?.readyState !== WebSocket.OPEN) return
      if (Date.now()-lastReply > 25000) socket.close()
      else socket.send('resync')
    }, 10000)
    connect()
    return () => {
      closed = true; clearTimeout(timer); clearInterval(heartbeat); socket?.close()
      window.removeEventListener('offline', offline); window.removeEventListener('online', online)
    }
  }, [])
}
