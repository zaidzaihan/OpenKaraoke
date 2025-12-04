from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect


class Room:
    def __init__(self):
        self.clients: List[WebSocket] = []
        self.host: WebSocket | None = None
        self.control_state = 'Pause'
        self.queue: List[dict] = []
        self.user_map:Dict[WebSocket, str] = {}


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        # str = room_id

    async def connect(self, websocket: WebSocket, room_id: str, username: str, is_host: bool = False):
    # Only allow creating rooms for hosts
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
        room.user_map[websocket] = username  # Add this line
        
        if (is_host):
            room.host = websocket

        await self.broadcast(room_id, {"type": "user_joined", "username": username, "is_host": is_host})
        return True

    async def disconnect(self, websocket: WebSocket, room_id: str):
        room = self.rooms.get(room_id)
        if not room:
            return
        
        # Get username before removing
        username = room.user_map.get(websocket)
        
        if websocket in room.clients:
            room.clients.remove(websocket)
            
        # Remove from user map
        if websocket in room.user_map:
            del room.user_map[websocket]
        
        # Broadcast user left event
        if username:
            await self.broadcast(room_id, {
                "type": "user_left",
                "username": username
            })
        
        # Clean up empty rooms
        if not room.clients:
            del self.rooms[room_id]
            
    async def broadcast(self, room_id: str, message: dict):
        room = self.rooms.get(room_id)
        if not room:
            return
        for client in room.clients:
            await client.send_json(message)

    async def handle_control(self, websocket: WebSocket, room_id: str, data: dict, username: str):
        room = self.rooms.get(room_id)
        if not room:
            return

        command = data.get("command")
        if command not in ["Play", "Pause", "Next", "Back"]:
            await websocket.send_json({"error": f"unknown command: {command}"})
            return
        room.control_state = command

        await self.broadcast(room_id, {"type": "control", "command": command, "username": username})

    async def enqueue_song(self, room_id: str, song: dict, username: str):
        room = self.rooms.get(room_id)
        if not song:
            return
        if not room:
            return
        queue_item = {
            "song": song,
            "added_by": username
        }
        room.queue.append(queue_item)
        # update 
        await self.send_queue(room_id)

        # if song is == 1, proceed to play

        if len(room.queue) == 1:
            await self.broadcast(room_id, {
                "type": "control", 
                "command": "Play", 
                "song": song,
                "username": username
            })
        room.control_state = "Play"
        
    # for sending queue list on host/ client
    async def send_queue(self, room_id: str):
        room = self.rooms.get(room_id)
        if not room:
            return

        await self.broadcast(room_id, {"type": "queue_list", "list": room.queue})

        # If there’s a "next" song
        if len(room.queue) > 1:
            await self.broadcast(room_id, {"type": "next_song", "song": room.queue[1]})


    async def handle_song_ended(self, room_id: str, username: str):
        room = self.rooms.get(room_id)
        if not room or not room.queue:
            return

        # Remove the song that just finished playing
        finished_song = room.queue.pop(0)

        # Broadcast queue update (remove first item)
        await self.send_queue(room_id)

        # If there are more songs, play the next one
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
            # Queue is empty — notify everyone
            await self.broadcast(room_id, {
                "type": "control",
                "command": "Pause",
                "username": "Host"
            })
            await self.broadcast(room_id, {
                "type": "song_ended"
            })
            room.control_state = "Pause"

