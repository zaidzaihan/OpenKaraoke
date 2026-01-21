from typing import Dict, List
from fastapi import WebSocket


class Room:
    def __init__(self):
        self.clients: List[WebSocket] = []
        self.host: WebSocket | None = None
        self.control_state = "Pause"
        self.queue: List[dict] = []
        self.user_map: Dict[WebSocket, str] = {}


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        username: str,
        is_host: bool = False,
    ):
        if room_id not in self.rooms:
            if not is_host:
                await websocket.send_json({
                    "type": "error",
                    "message": "Room does not exist"
                })
                await websocket.close()
                return False

            self.rooms[room_id] = Room()

        room = self.rooms[room_id]
        room.clients.append(websocket)
        room.user_map[websocket] = username

        if is_host:
            room.host = websocket

        await self.broadcast(room_id, {
            "type": "user_joined",
            "username": username,
            "is_host": is_host
        })

        # Send current queue immediately on join
        await websocket.send_json({
            "type": "queue_list",
            "list": room.queue
        })

        return True

    async def disconnect(self, websocket: WebSocket, room_id: str):
        room = self.rooms.get(room_id)
        if not room:
            return

        username = room.user_map.get(websocket)

        if websocket in room.clients:
            room.clients.remove(websocket)

        room.user_map.pop(websocket, None)

        if username:
            await self.broadcast(room_id, {
                "type": "user_left",
                "username": username
            })

        if not room.clients:
            del self.rooms[room_id]

    async def broadcast(self, room_id: str, message: dict):
        room = self.rooms.get(room_id)
        if not room:
            return

        for client in room.clients:
            await client.send_json(message)

    async def handle_control(
        self,
        websocket: WebSocket,
        room_id: str,
        data: dict,
        username: str
    ):
        room = self.rooms.get(room_id)
        if not room:
            return

        command = data.get("command")
        if command not in {"Play", "Pause", "Next", "Back"}:
            await websocket.send_json({
                "type": "error",
                "message": f"Unknown command: {command}"
            })
            return

        room.control_state = command

        await self.broadcast(room_id, {
            "type": "control",
            "command": command,
            "username": username
        })

    async def enqueue_song(self, room_id: str, song: dict, username: str):
        room = self.rooms.get(room_id)
        if not room or not song:
            return

        room.queue.append({
            "song": song,
            "added_by": username
        })

        await self.send_queue(room_id)

        # Auto-play if first song
        if len(room.queue) == 1:
            await self.broadcast(room_id, {
                "type": "control",
                "command": "Play",
                "song": song,
                "username": username
            })
            room.control_state = "Play"

    async def send_queue(self, room_id: str):
        room = self.rooms.get(room_id)
        if not room:
            return

        await self.broadcast(room_id, {
            "type": "queue_list",
            "list": room.queue
        })

    async def handle_song_ended(self, room_id: str, username: str):
        room = self.rooms.get(room_id)
        if not room or not room.queue:
            return

        # Remove finished song
        room.queue.pop(0)

        await self.send_queue(room_id)

        if room.queue:
            next_song = room.queue[0]["song"]
            await self.broadcast(room_id, {
                "type": "control",
                "command": "Play",
                "song": next_song,
                "username": username
            })
            room.control_state = "Play"
        else:
            await self.broadcast(room_id, {
                "type": "control",
                "command": "Pause",
                "username": "Host"
            })
            await self.broadcast(room_id, {
                "type": "song_ended"
            })
            room.control_state = "Pause"

    async def handle_comment(self, room_id: str, comment: str, username: str):
        """Handle short-lived comments that broadcast to all users"""
        room = self.rooms.get(room_id)
        if not room:
            return

        # Broadcast comment to all clients in the room
        await self.broadcast(room_id, {
            "type": "comment",
            "comment": comment,
            "username": username
        })