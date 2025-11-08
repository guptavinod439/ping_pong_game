import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const INPUT_INTERVAL = 1000 / 30;

const defaultState = {
  players: {
    1: { y: (500 - 80) / 2 },
    2: { y: (500 - 80) / 2 },
  },
  ball: { x: 800 / 2, y: 500 / 2 },
  score: { 1: 0, 2: 0 },
  bounds: { width: 800, height: 500 },
  paddle: { w: 12, h: 80 },
  ballRadius: 8,
};

function normaliseState(incoming) {
  const source = incoming ?? {};
  const players = source.players ?? {};
  const score = source.score ?? {};

  const resolvePlayerY = (key) => {
    if (players[key]?.y != null) return players[key].y;
    const asString = String(key);
    if (players[asString]?.y != null) return players[asString].y;
    return defaultState.players[key].y;
  };

  const resolveScore = (key) => {
    if (score[key] != null) return score[key];
    const asString = String(key);
    if (score[asString] != null) return score[asString];
    return defaultState.score[key];
  };

  return {
    players: {
      1: { y: resolvePlayerY(1) },
      2: { y: resolvePlayerY(2) },
    },
    ball: {
      x: source.ball?.x ?? defaultState.ball.x,
      y: source.ball?.y ?? defaultState.ball.y,
    },
    score: {
      1: resolveScore(1),
      2: resolveScore(2),
    },
    bounds: {
      width: source.bounds?.width ?? defaultState.bounds.width,
      height: source.bounds?.height ?? defaultState.bounds.height,
    },
    paddle: {
      w: source.paddle?.w ?? defaultState.paddle.w,
      h: source.paddle?.h ?? defaultState.paddle.h,
    },
    ballRadius: source.ballRadius ?? defaultState.ballRadius,
  };
}

const keyMap = {
  KeyW: 'up',
  KeyS: 'down',
  ArrowUp: 'up',
  ArrowDown: 'down',
  KeyA: 'up',
  KeyD: 'down',
};

function useWebSocketState() {
  const [assignedPlayer, setAssignedPlayer] = useState(null);
  const [state, setState] = useState(defaultState);
  const wsRef = useRef(null);
  const inputRef = useRef({ up: false, down: false });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const room = params.get('room') ?? 'default';
    const requestedPlayer = params.get('player') ?? 'auto';
    const baseUrl = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';
    const url = `${baseUrl}?room=${encodeURIComponent(room)}&player=${encodeURIComponent(requestedPlayer)}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.addEventListener('message', (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'assign') {
        setAssignedPlayer(data.player === null ? 'spectator' : data.player);
      } else if (data.type === 'state') {
        setState(normaliseState(data));
      }
    });

    ws.addEventListener('close', () => {
      wsRef.current = null;
      setAssignedPlayer(null);
    });

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        return;
      }
      wsRef.current.send(
        JSON.stringify({
          type: 'input',
          up: inputRef.current.up,
          down: inputRef.current.down,
        })
      );
    }, INPUT_INTERVAL);

    return () => clearInterval(interval);
  }, []);

  const updateInput = useCallback((up, down) => {
    inputRef.current = { up, down };
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'input',
          up,
          down,
        })
      );
    }
  }, []);

  const resendCurrentInput = useCallback(() => {
    updateInput(inputRef.current.up, inputRef.current.down);
  }, [updateInput]);

  return { state, assignedPlayer, updateInput, resendCurrentInput };
}

function App() {
  const { state, assignedPlayer, updateInput, resendCurrentInput } = useWebSocketState();
  const canvasRef = useRef(null);
  const keysRef = useRef({ up: false, down: false });

  useEffect(() => {
    const handleKey = (event, isDown) => {
      const action = keyMap[event.code];
      if (!action) return;
      event.preventDefault();
      const current = keysRef.current;
      if (current[action] === isDown) {
        return;
      }
      const next = { ...current, [action]: isDown };
      keysRef.current = next;
      updateInput(next.up, next.down);
    };

    const keydown = (event) => handleKey(event, true);
    const keyup = (event) => handleKey(event, false);

    window.addEventListener('keydown', keydown);
    window.addEventListener('keyup', keyup);

    return () => {
      window.removeEventListener('keydown', keydown);
      window.removeEventListener('keyup', keyup);
    };
  }, [updateInput]);

  useEffect(() => {
    resendCurrentInput();
  }, [assignedPlayer, resendCurrentInput]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { bounds, paddle, ballRadius, players, ball, score } = state;
    canvas.width = bounds.width;
    canvas.height = bounds.height;

    ctx.fillStyle = '#111';
    ctx.fillRect(0, 0, bounds.width, bounds.height);

    ctx.fillStyle = '#fff';
    ctx.fillRect(10, players[1].y, paddle.w, paddle.h);
    ctx.fillRect(bounds.width - 10 - paddle.w, players[2].y, paddle.w, paddle.h);

    ctx.beginPath();
    ctx.arc(ball.x, ball.y, ballRadius, 0, Math.PI * 2);
    ctx.fill();

    ctx.font = '20px sans-serif';
    ctx.fillText(String(score[1]), bounds.width / 4, 30);
    ctx.fillText(String(score[2]), (bounds.width * 3) / 4, 30);
  }, [state]);

  const roleLabel = useMemo(() => {
    if (assignedPlayer === 1 || assignedPlayer === 2) {
      return `Connected as Player ${assignedPlayer}`;
    }
    if (assignedPlayer === null) {
      return 'Connecting...';
    }
    return 'Spectator';
  }, [assignedPlayer]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
        color: '#fff',
        background: '#222',
        minHeight: '100vh',
        padding: '20px',
        boxSizing: 'border-box',
      }}
    >
      <div>{roleLabel}</div>
      <canvas ref={canvasRef} style={{ border: '1px solid #555' }} />
      <div style={{ fontSize: '12px', opacity: 0.8 }}>
        Controls: W/S/A/D or Arrow Up/Down
      </div>
    </div>
  );
}

export default App;
