let active:WebSocket|null=null
let latest:number[][]=[]
export function setStream(socket:WebSocket|null) {active=socket;if(socket?.readyState===WebSocket.OPEN&&latest.length)requestChunks(latest)}
export function requestChunks(coordinates:number[][]) {
  latest=coordinates
  if(active?.readyState===WebSocket.OPEN)active.send(JSON.stringify({type:'viewport',chunks:coordinates.slice(0,25)}))
}
