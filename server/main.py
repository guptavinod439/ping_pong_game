import asyncio
import math
import random
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


TICK_RATE = 60  # FPS
FIELD_WIDTH = 800
FIELD_HEIGHT = 500
PADDLE_WIDTH = 12
PADDLE_HEIGHT = 80
PADDLE_SPEED = 6
BALL_RADIUS = 8
BALL_SPEED = 5


class PlayerState:
    def __init__(self) -> None:
        self.y = (FIELD_HEIGHT - PADDLE_HEIGHT) / 2
        self.input_up = False
        self.input_down = False


class GameRoom:
    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.players: Dict[int, PlayerState] = {1: PlayerState(), 2: PlayerState()}
        self.score = {1: 0, 2: 0}
        self.ball = {
            "x": FIELD_WIDTH / 2,
            "y": FIELD_HEIGHT / 2,
            "vx": BALL_SPEED if random.random() < 0.5 else -BALL_SPEED,
            "vy": random.uniform(-2.0, 2.0),
        }
        self.connections: List[WebSocket] = []
        self.inputs_lock = asyncio.Lock()
        self.loop_task: Optional[asyncio.Task] = None
        self.bounds = {"width": FIELD_WIDTH, "height": FIELD_HEIGHT}
        self.paddle_info = {"w": PADDLE_WIDTH, "h": PADDLE_HEIGHT}

    def start(self) -> None:
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.create_task(self.run())

    async def reset_ball(self, direction: Optional[int] = None) -> None:
        self.ball["x"] = FIELD_WIDTH / 2
        self.ball["y"] = FIELD_HEIGHT / 2
        x_dir = direction if direction in (-1, 1) else random.choice([-1, 1])
        self.ball["vx"] = BALL_SPEED * x_dir
        self.ball["vy"] = random.uniform(-2.0, 2.0)

    async def update_players(self) -> None:
        for idx, state in self.players.items():
            if state.input_up and not state.input_down:
                state.y -= PADDLE_SPEED
            elif state.input_down and not state.input_up:
                state.y += PADDLE_SPEED
            state.y = max(0, min(FIELD_HEIGHT - PADDLE_HEIGHT, state.y))

    async def update_ball(self) -> None:
        self.ball["x"] += self.ball["vx"]
        self.ball["y"] += self.ball["vy"]

        # Wall collisions
        if self.ball["y"] - BALL_RADIUS <= 0:
            self.ball["y"] = BALL_RADIUS
            self.ball["vy"] *= -1
        elif self.ball["y"] + BALL_RADIUS >= FIELD_HEIGHT:
            self.ball["y"] = FIELD_HEIGHT - BALL_RADIUS
            self.ball["vy"] *= -1

        # Paddle collisions
        paddle_left = {
            "x": 10,
            "y": self.players[1].y,
            "w": PADDLE_WIDTH,
            "h": PADDLE_HEIGHT,
        }
        paddle_right = {
            "x": FIELD_WIDTH - 10 - PADDLE_WIDTH,
            "y": self.players[2].y,
            "w": PADDLE_WIDTH,
            "h": PADDLE_HEIGHT,
        }

        if self._ball_intersects(paddle_left) and self.ball["vx"] < 0:
            self.ball["x"] = paddle_left["x"] + paddle_left["w"] + BALL_RADIUS
            self.ball["vx"] *= -1
            self._add_spin(paddle_left)
        elif self._ball_intersects(paddle_right) and self.ball["vx"] > 0:
            self.ball["x"] = paddle_right["x"] - BALL_RADIUS
            self.ball["vx"] *= -1
            self._add_spin(paddle_right)

        # Scoring
        if self.ball["x"] < -BALL_RADIUS:
            self.score[2] += 1
            await self.reset_ball(direction=1)
        elif self.ball["x"] > FIELD_WIDTH + BALL_RADIUS:
            self.score[1] += 1
            await self.reset_ball(direction=-1)

    def _ball_intersects(self, paddle: Dict[str, float]) -> bool:
        closest_x = max(paddle["x"], min(self.ball["x"], paddle["x"] + paddle["w"]))
        closest_y = max(paddle["y"], min(self.ball["y"], paddle["y"] + paddle["h"]))
        dx = self.ball["x"] - closest_x
        dy = self.ball["y"] - closest_y
        return dx * dx + dy * dy <= BALL_RADIUS * BALL_RADIUS

    def _add_spin(self, paddle: Dict[str, float]) -> None:
        offset = (self.ball["y"] - (paddle["y"] + paddle["h"] / 2)) / (paddle["h"] / 2)
        self.ball["vy"] += offset * 1.5
        speed = math.hypot(self.ball["vx"], self.ball["vy"])
        scale = BALL_SPEED / max(speed, 1e-5)
        self.ball["vx"] *= scale
        self.ball["vy"] *= scale

    async def broadcast_state(self) -> None:
        payload = {
            "type": "state",
            "players": {"1": {"y": self.players[1].y}, "2": {"y": self.players[2].y}},
            "ball": {"x": self.ball["x"], "y": self.ball["y"]},
            "score": {"1": self.score[1], "2": self.score[2]},
            "bounds": self.bounds,
            "paddle": self.paddle_info,
            "ballRadius": BALL_RADIUS,
        }
        disconnected: List[WebSocket] = []
        for ws in list(self.connections):
            try:
                await ws.send_json(payload)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            await self.unregister(ws)

    async def run(self) -> None:
        tick_duration = 1.0 / TICK_RATE
        while True:
            start = time.perf_counter()
            async with self.inputs_lock:
                await self.update_players()
                await self.update_ball()
            await self.broadcast_state()
            elapsed = time.perf_counter() - start
            await asyncio.sleep(max(0, tick_duration - elapsed))

    async def register(self, websocket: WebSocket) -> None:
        self.connections.append(websocket)

    async def unregister(self, websocket: WebSocket) -> None:
        if websocket in self.connections:
            self.connections.remove(websocket)

    def set_input(self, player: int, *, up: bool, down: bool) -> None:
        if player in self.players:
            self.players[player].input_up = up
            self.players[player].input_down = down


class GameManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, GameRoom] = {}

    def get_room(self, room_id: str) -> GameRoom:
        if room_id not in self.rooms:
            self.rooms[room_id] = GameRoom(room_id)
            self.rooms[room_id].start()
        return self.rooms[room_id]

    def assign_player(self, room: GameRoom, requested: Optional[int]) -> Optional[int]:
        if requested in (1, 2) and not self._player_taken(room, requested):
            return requested
        if not self._player_taken(room, 1):
            return 1
        if not self._player_taken(room, 2):
            return 2
        return None

    def _player_taken(self, room: GameRoom, player: int) -> bool:
        for ws in room.connections:
            assigned = getattr(ws, "assigned_player", None)
            if assigned == player:
                return True
        return False


game_manager = GameManager()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, room: str = "default", player: str = "auto") -> None:
    await websocket.accept()
    game_room = game_manager.get_room(room)
    await game_room.register(websocket)

    requested_player: Optional[int]
    if player in {"1", "2"}:
        requested_player = int(player)
    else:
        requested_player = None

    assigned_player = game_manager.assign_player(game_room, requested_player)
    websocket.assigned_player = assigned_player  # type: ignore[attr-defined]

    await websocket.send_json({"type": "assign", "player": assigned_player})

    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "input" and assigned_player is not None:
                up = bool(message.get("up"))
                down = bool(message.get("down"))
                async with game_room.inputs_lock:
                    game_room.set_input(assigned_player, up=up, down=down)
    except WebSocketDisconnect:
        pass
    finally:
        async with game_room.inputs_lock:
            if assigned_player is not None:
                game_room.set_input(assigned_player, up=False, down=False)
        await game_room.unregister(websocket)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}
