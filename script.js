const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");

const TILE_W = 36;
const TILE_H = 18;
const CHUNK_SIZE = 16;
const VIEW_DISTANCE = 5;
const SEA_LEVEL = 10;

const textures = createTextures();

const keys = new Set();
const player = {
  x: 0,
  y: 0,
  z: 0,
  speed: 2.2,
  rotation: 0,
  step: 0,
};

const chunks = new Map();

function resize() {
  canvas.width = window.innerWidth * devicePixelRatio;
  canvas.height = window.innerHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}

window.addEventListener("resize", resize);
resize();

window.addEventListener("keydown", (event) => {
  keys.add(event.key.toLowerCase());
  if (event.key === "q") {
    player.rotation = (player.rotation + 3) % 4;
  }
  if (event.key === "e") {
    player.rotation = (player.rotation + 1) % 4;
  }
});

window.addEventListener("keyup", (event) => {
  keys.delete(event.key.toLowerCase());
});

function loop(timestamp) {
  updatePlayer();
  updateChunks();
  renderWorld(timestamp);
  requestAnimationFrame(loop);
}

requestAnimationFrame(loop);

function updatePlayer() {
  const speed = keys.has("shift") ? player.speed * 1.8 : player.speed;
  const dir = { x: 0, y: 0 };
  if (keys.has("w")) dir.y -= 1;
  if (keys.has("s")) dir.y += 1;
  if (keys.has("a")) dir.x -= 1;
  if (keys.has("d")) dir.x += 1;
  if (dir.x !== 0 || dir.y !== 0) {
    const length = Math.hypot(dir.x, dir.y) || 1;
    dir.x /= length;
    dir.y /= length;
    const rotated = rotateVector(dir.x, dir.y, player.rotation);
    player.x += rotated.x * speed * 0.1;
    player.y += rotated.y * speed * 0.1;
    player.step += speed * 0.1;
  }
  player.z = sampleHeight(player.x, player.y) + 2.5;
}

function updateChunks() {
  const centerChunkX = Math.floor(player.x / CHUNK_SIZE);
  const centerChunkY = Math.floor(player.y / CHUNK_SIZE);
  for (let cy = centerChunkY - VIEW_DISTANCE; cy <= centerChunkY + VIEW_DISTANCE; cy += 1) {
    for (let cx = centerChunkX - VIEW_DISTANCE; cx <= centerChunkX + VIEW_DISTANCE; cx += 1) {
      const key = `${cx},${cy}`;
      if (!chunks.has(key)) {
        chunks.set(key, generateChunk(cx, cy));
      }
    }
  }
}

function renderWorld(timestamp) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(canvas.width / 2, canvas.height / 2 + 40);

  const blocks = collectVisibleBlocks();
  blocks.sort((a, b) => a.depth - b.depth);

  for (const block of blocks) {
    drawBlock(block);
  }

  ctx.restore();
  drawHud();
  drawHand(timestamp);
}

function collectVisibleBlocks() {
  const result = [];
  const originX = Math.floor(player.x);
  const originY = Math.floor(player.y);
  const radius = CHUNK_SIZE * (VIEW_DISTANCE - 1);
  for (let y = originY - radius; y <= originY + radius; y += 1) {
    for (let x = originX - radius; x <= originX + radius; x += 1) {
      const height = sampleHeight(x, y);
      const waterHeight = Math.max(SEA_LEVEL - height, 0);
      for (let z = 0; z <= height; z += 1) {
        const blockType = z === height ? pickSurfaceBlock(height) : "dirt";
        result.push(createBlock(x, y, z, blockType));
      }
      for (let w = 1; w <= waterHeight; w += 1) {
        result.push(createBlock(x, y, height + w, "water"));
      }
    }
  }
  return result;
}

function createBlock(x, y, z, type) {
  const rotated = rotateCoord(x - player.x, y - player.y, player.rotation);
  const isoX = (rotated.x - rotated.y) * (TILE_W / 2);
  const isoY = (rotated.x + rotated.y) * (TILE_H / 2) - z * TILE_H;
  const depth = rotated.x + rotated.y + z * 0.6;
  return {
    x,
    y,
    z,
    type,
    isoX,
    isoY,
    depth,
  };
}

function drawBlock(block) {
  const texture = textures[block.type];
  const top = texture.top;
  const side = texture.side;
  const shadow = texture.shadow;

  ctx.save();
  ctx.translate(block.isoX, block.isoY);

  drawTopFace(top);
  drawSideFaces(side, shadow);

  ctx.restore();
}

function drawTopFace(pattern) {
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(TILE_W / 2, TILE_H / 2);
  ctx.lineTo(0, TILE_H);
  ctx.lineTo(-TILE_W / 2, TILE_H / 2);
  ctx.closePath();
  ctx.fillStyle = pattern;
  ctx.fill();
}

function drawSideFaces(sideColor, shadowColor) {
  ctx.fillStyle = shadowColor;
  ctx.beginPath();
  ctx.moveTo(0, TILE_H);
  ctx.lineTo(TILE_W / 2, TILE_H / 2);
  ctx.lineTo(TILE_W / 2, TILE_H / 2 + TILE_H);
  ctx.lineTo(0, TILE_H * 2);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = sideColor;
  ctx.beginPath();
  ctx.moveTo(0, TILE_H);
  ctx.lineTo(-TILE_W / 2, TILE_H / 2);
  ctx.lineTo(-TILE_W / 2, TILE_H / 2 + TILE_H);
  ctx.lineTo(0, TILE_H * 2);
  ctx.closePath();
  ctx.fill();
}

function createTextures() {
  return {
    grass: buildTexture("#48b05e", "#2f7a3b"),
    dirt: buildTexture("#8b5a2b", "#6a3f1c"),
    stone: buildTexture("#8a8f9d", "#6b6f7b"),
    sand: buildTexture("#d8c28a", "#b79b60"),
    water: buildTexture("#3b8eea", "#2461b4", 0.6),
  };
}

function buildTexture(primary, secondary, alpha = 1) {
  const canvas = document.createElement("canvas");
  const size = 16;
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");

  context.fillStyle = primary;
  context.globalAlpha = alpha;
  context.fillRect(0, 0, size, size);

  context.fillStyle = secondary;
  context.globalAlpha = alpha;
  for (let i = 0; i < 40; i += 1) {
    const x = Math.floor(Math.random() * size);
    const y = Math.floor(Math.random() * size);
    context.fillRect(x, y, 1, 1);
  }

  return {
    top: ctx.createPattern(canvas, "repeat"),
    side: shade(primary, 0.8),
    shadow: shade(primary, 0.6),
  };
}

function shade(color, factor) {
  const rgb = color.match(/\w\w/g).map((v) => parseInt(v, 16));
  const shaded = rgb.map((channel) => Math.max(0, Math.min(255, channel * factor)));
  return `rgb(${shaded[0]}, ${shaded[1]}, ${shaded[2]})`;
}

function rotateCoord(x, y, rotation) {
  switch (rotation) {
    case 0:
      return { x, y };
    case 1:
      return { x: -y, y: x };
    case 2:
      return { x: -x, y: -y };
    case 3:
      return { x: y, y: -x };
    default:
      return { x, y };
  }
}

function rotateVector(x, y, rotation) {
  return rotateCoord(x, y, rotation);
}

function generateChunk(cx, cy) {
  const heights = Array.from({ length: CHUNK_SIZE }, () => Array(CHUNK_SIZE).fill(0));
  for (let y = 0; y < CHUNK_SIZE; y += 1) {
    for (let x = 0; x < CHUNK_SIZE; x += 1) {
      const worldX = cx * CHUNK_SIZE + x;
      const worldY = cy * CHUNK_SIZE + y;
      const height = Math.floor(getNoiseHeight(worldX, worldY));
      heights[y][x] = height;
    }
  }
  return { cx, cy, heights };
}

function sampleHeight(x, y) {
  const cx = Math.floor(x / CHUNK_SIZE);
  const cy = Math.floor(y / CHUNK_SIZE);
  const key = `${cx},${cy}`;
  if (!chunks.has(key)) {
    chunks.set(key, generateChunk(cx, cy));
  }
  const chunk = chunks.get(key);
  const localX = ((Math.floor(x) % CHUNK_SIZE) + CHUNK_SIZE) % CHUNK_SIZE;
  const localY = ((Math.floor(y) % CHUNK_SIZE) + CHUNK_SIZE) % CHUNK_SIZE;
  return chunk.heights[localY][localX];
}

function getNoiseHeight(x, y) {
  const scale = 0.08;
  const elevation = fbm(x * scale, y * scale, 4);
  return elevation * 14 + 6;
}

function fbm(x, y, octaves) {
  let value = 0;
  let amplitude = 1;
  let frequency = 1;
  let max = 0;
  for (let i = 0; i < octaves; i += 1) {
    value += amplitude * noise2D(x * frequency, y * frequency);
    max += amplitude;
    amplitude *= 0.5;
    frequency *= 2;
  }
  return value / max;
}

function noise2D(x, y) {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const x1 = x0 + 1;
  const y1 = y0 + 1;

  const sx = smoothstep(x - x0);
  const sy = smoothstep(y - y0);

  const n0 = hash(x0, y0);
  const n1 = hash(x1, y0);
  const ix0 = lerp(n0, n1, sx);
  const n2 = hash(x0, y1);
  const n3 = hash(x1, y1);
  const ix1 = lerp(n2, n3, sx);
  return lerp(ix0, ix1, sy);
}

function hash(x, y) {
  let h = x * 374761393 + y * 668265263;
  h = (h ^ (h >> 13)) * 1274126177;
  return ((h ^ (h >> 16)) >>> 0) / 4294967295;
}

function smoothstep(t) {
  return t * t * (3 - 2 * t);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function pickSurfaceBlock(height) {
  if (height < SEA_LEVEL - 2) return "sand";
  if (height < SEA_LEVEL + 2) return "grass";
  if (height < SEA_LEVEL + 6) return "dirt";
  return "stone";
}

function drawHud() {
  ctx.save();
  ctx.fillStyle = "rgba(10, 15, 23, 0.6)";
  ctx.fillRect(24, canvas.height - 100, 240, 70);
  ctx.fillStyle = "#e5f1ff";
  ctx.font = "14px 'Inter', sans-serif";
  ctx.fillText(`X: ${player.x.toFixed(1)}`, 36, canvas.height - 70);
  ctx.fillText(`Y: ${player.y.toFixed(1)}`, 36, canvas.height - 50);
  ctx.fillText(`Чанков: ${chunks.size}`, 36, canvas.height - 30);
  ctx.restore();
}

function drawHand(timestamp) {
  const swing = Math.sin(timestamp / 120) * 8 * (keys.has("w") || keys.has("a") || keys.has("s") || keys.has("d") ? 1 : 0.3);
  const baseX = canvas.width - 180;
  const baseY = canvas.height - 120;

  ctx.save();
  ctx.translate(baseX, baseY + swing);
  ctx.rotate(-0.25 + Math.sin(timestamp / 500) * 0.05);

  ctx.fillStyle = "#c58a5a";
  ctx.fillRect(0, 0, 80, 48);
  ctx.fillStyle = "#6a8fc7";
  ctx.fillRect(0, 32, 80, 36);

  ctx.fillStyle = "rgba(0,0,0,0.25)";
  ctx.fillRect(4, 4, 72, 8);

  ctx.restore();
}
