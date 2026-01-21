from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from rooms import RoomManager, Room
import random
from youtube_search import YoutubeSearch
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
room_manager = RoomManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Your Next.js frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/create-room")
def create_room():
    while True:
        room_id = str(random.randint(100000, 999999))
        if room_id not in room_manager.rooms:
            room_manager.rooms[room_id] = Room()
            return {"room_id": room_id}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    try:
        init_data = await websocket.receive_json()
        username = init_data.get("username")
        is_host = init_data.get("is_host", False)
        connected = await room_manager.connect(websocket, room_id, username, is_host)
        if not connected:
            return 

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "control":
                await room_manager.handle_control(websocket, room_id, data, username)
            elif msg_type == "queue_update":
                await room_manager.enqueue_song(room_id, data["song"], username)
            elif msg_type == "song_ended":
                await room_manager.handle_song_ended(room_id, username)
            elif msg_type == "comment":
                # Handle comment messages
                comment = data.get("comment", "")
                if comment.strip():  # Only process non-empty comments
                    await room_manager.handle_comment(room_id, comment, username)
            else:
                await room_manager.broadcast(room_id, data)
                
    except WebSocketDisconnect:
        # This automatically handles disconnections (browser close, network issues, etc.)
        await room_manager.disconnect(websocket, room_id)   
        
@app.get("/search")
def searchYT(query: str):
    results = YoutubeSearch(query + 'karaoke', max_results=10).to_dict()
    cleaned = []
    for r in results:
        video_id = r["id"]
        cleaned.append({
            "title": r["title"],
            "duration": r["duration"],
            "thumbnail": r["thumbnails"][0],
            "url": f"https://www.youtube.com/watch?v={video_id}"
        })
        
    return {"results": cleaned}