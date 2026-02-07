import json
import math
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pyglet
from pyglet.gl import (
    GL_BLEND,
    GL_CULL_FACE,
    GL_DEPTH_TEST,
    GL_QUADS,
    GL_SRC_ALPHA,
    GL_ONE_MINUS_SRC_ALPHA,
    glBlendFunc,
    glEnable,
    glLoadIdentity,
    glMatrixMode,
    glRotatef,
    glTranslatef,
    glViewport,
    gluPerspective,
    GL_MODELVIEW,
    GL_PROJECTION,
)

Vec3 = Tuple[float, float, float]

CHUNK_SIZE = 16
CHUNK_HEIGHT = 256
BLOCK_AIR = 0
BLOCK_GRASS = 1
BLOCK_DIRT = 2
BLOCK_STONE = 3
BLOCK_WOOD = 4
BLOCK_TYPES = [BLOCK_GRASS, BLOCK_DIRT, BLOCK_STONE, BLOCK_WOOD]

SAVE_DIR = "world_saves"
TEXTURE_FILE = "terrain.png"


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


class PerlinNoise:
    def __init__(self, seed: int = 0) -> None:
        self.permutation = list(range(256))
        randomizer = random.Random(seed)
        randomizer.shuffle(self.permutation)
        self.permutation *= 2

    def grad(self, hash_value: int, x: float, y: float, z: float) -> float:
        h = hash_value & 15
        u = x if h < 8 else y
        v = y if h < 4 else (x if h in (12, 14) else z)
        return ((u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v))

    def noise(self, x: float, y: float, z: float) -> float:
        xi = int(math.floor(x)) & 255
        yi = int(math.floor(y)) & 255
        zi = int(math.floor(z)) & 255

        xf = x - math.floor(x)
        yf = y - math.floor(y)
        zf = z - math.floor(z)

        u = fade(xf)
        v = fade(yf)
        w = fade(zf)

        p = self.permutation
        aaa = p[p[p[xi] + yi] + zi]
        aba = p[p[p[xi] + yi + 1] + zi]
        aab = p[p[p[xi] + yi] + zi + 1]
        abb = p[p[p[xi] + yi + 1] + zi + 1]
        baa = p[p[p[xi + 1] + yi] + zi]
        bba = p[p[p[xi + 1] + yi + 1] + zi]
        bab = p[p[p[xi + 1] + yi] + zi + 1]
        bbb = p[p[p[xi + 1] + yi + 1] + zi + 1]

        x1 = lerp(self.grad(aaa, xf, yf, zf), self.grad(baa, xf - 1, yf, zf), u)
        x2 = lerp(self.grad(aba, xf, yf - 1, zf), self.grad(bba, xf - 1, yf - 1, zf), u)
        y1 = lerp(x1, x2, v)

        x3 = lerp(self.grad(aab, xf, yf, zf - 1), self.grad(bab, xf - 1, yf, zf - 1), u)
        x4 = lerp(self.grad(abb, xf, yf - 1, zf - 1), self.grad(bbb, xf - 1, yf - 1, zf - 1), u)
        y2 = lerp(x3, x4, v)

        return (lerp(y1, y2, w) + 1) / 2


class TextureHandler:
    def __init__(self, filename: str) -> None:
        self.texture = self._load_texture(filename)
        self.uv_map = {
            BLOCK_GRASS: (0, 0),
            BLOCK_DIRT: (1, 0),
            BLOCK_STONE: (2, 0),
            BLOCK_WOOD: (3, 0),
        }

    def _load_texture(self, filename: str) -> pyglet.image.Texture:
        if os.path.exists(filename):
            image = pyglet.image.load(filename)
            image = image.get_texture()
        else:
            image = self._generate_procedural_atlas()
        image.mag_filter = pyglet.gl.GL_NEAREST
        image.min_filter = pyglet.gl.GL_NEAREST
        return image

    def _generate_procedural_atlas(self) -> pyglet.image.Texture:
        atlas = pyglet.image.Texture.create(64, 16)
        colors = [
            (95, 159, 53, 255),
            (134, 96, 67, 255),
            (120, 120, 120, 255),
            (102, 76, 50, 255),
        ]
        for i, color in enumerate(colors):
            pattern = pyglet.image.SolidColorImagePattern(color)
            tile = pattern.create_image(16, 16)
            atlas.blit_into(tile, i * 16, 0, 0)
        return atlas

    def get_tex_coords(self, block_type: int) -> List[float]:
        atlas_size = 64
        tile_size = 16
        u, v = self.uv_map.get(block_type, (0, 0))
        x = u * tile_size / atlas_size
        y = v * tile_size / atlas_size
        dx = tile_size / atlas_size
        dy = tile_size / atlas_size
        return [
            x, y,
            x + dx, y,
            x + dx, y + dy,
            x, y + dy,
        ]


@dataclass
class Block:
    block_type: int


class Chunk:
    def __init__(self, world: "World", chunk_x: int, chunk_z: int) -> None:
        self.world = world
        self.chunk_x = chunk_x
        self.chunk_z = chunk_z
        self.blocks = [[[BLOCK_AIR for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_HEIGHT)] for _ in range(CHUNK_SIZE)]
        self.vertex_list = None
        self.needs_remesh = True

    def set_block(self, x: int, y: int, z: int, block_type: int) -> None:
        if 0 <= y < CHUNK_HEIGHT:
            self.blocks[x][y][z] = block_type
            self.needs_remesh = True

    def get_block(self, x: int, y: int, z: int) -> int:
        if 0 <= y < CHUNK_HEIGHT:
            return self.blocks[x][y][z]
        return BLOCK_AIR

    def generate(self) -> None:
        noise = self.world.noise
        for x in range(CHUNK_SIZE):
            for z in range(CHUNK_SIZE):
                world_x = self.chunk_x * CHUNK_SIZE + x
                world_z = self.chunk_z * CHUNK_SIZE + z
                height = int(noise.noise(world_x * 0.05, 0, world_z * 0.05) * 40 + 64)
                for y in range(CHUNK_HEIGHT):
                    density = noise.noise(world_x * 0.08, y * 0.08, world_z * 0.08)
                    if y < height and density > 0.35:
                        if y == height - 1:
                            block_type = BLOCK_GRASS
                        elif y > height - 4:
                            block_type = BLOCK_DIRT
                        else:
                            block_type = BLOCK_STONE
                        self.blocks[x][y][z] = block_type

    def serialize(self) -> Dict:
        return {
            "chunk_x": self.chunk_x,
            "chunk_z": self.chunk_z,
            "blocks": self.blocks,
        }

    @classmethod
    def from_data(cls, world: "World", data: Dict) -> "Chunk":
        chunk = cls(world, data["chunk_x"], data["chunk_z"])
        chunk.blocks = data["blocks"]
        chunk.needs_remesh = True
        return chunk

    def rebuild_mesh(self, batch: pyglet.graphics.Batch, texture: TextureHandler) -> None:
        if self.vertex_list:
            self.vertex_list.delete()
            self.vertex_list = None

        vertices: List[float] = []
        tex_coords: List[float] = []

        for x in range(CHUNK_SIZE):
            for y in range(CHUNK_HEIGHT):
                for z in range(CHUNK_SIZE):
                    block_type = self.blocks[x][y][z]
                    if block_type == BLOCK_AIR:
                        continue
                    self._add_block_faces(vertices, tex_coords, x, y, z, block_type, texture)

        if vertices:
            self.vertex_list = batch.add(
                len(vertices) // 3,
                GL_QUADS,
                None,
                ("v3f/static", vertices),
                ("t2f/static", tex_coords),
            )
        self.needs_remesh = False

    def _add_block_faces(
        self,
        vertices: List[float],
        tex_coords: List[float],
        x: int,
        y: int,
        z: int,
        block_type: int,
        texture: TextureHandler,
    ) -> None:
        world_x = self.chunk_x * CHUNK_SIZE + x
        world_z = self.chunk_z * CHUNK_SIZE + z
        faces = [
            ((0, 0, -1), [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]),
            ((0, 0, 1), [(1, 0, 1), (0, 0, 1), (0, 1, 1), (1, 1, 1)]),
            ((-1, 0, 0), [(0, 0, 1), (0, 0, 0), (0, 1, 0), (0, 1, 1)]),
            ((1, 0, 0), [(1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)]),
            ((0, 1, 0), [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)]),
            ((0, -1, 0), [(0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)]),
        ]
        for normal, corners in faces:
            nx, ny, nz = normal
            neighbor = self.world.get_block(world_x + nx, y + ny, world_z + nz)
            if neighbor != BLOCK_AIR:
                continue
            for cx, cy, cz in corners:
                vertices.extend([world_x + cx, y + cy, world_z + cz])
            tex_coords.extend(texture.get_tex_coords(block_type))


class World:
    def __init__(self, seed: int = 0) -> None:
        self.chunks: Dict[Tuple[int, int], Chunk] = {}
        self.noise = PerlinNoise(seed)

    def get_chunk(self, chunk_x: int, chunk_z: int) -> Chunk:
        key = (chunk_x, chunk_z)
        if key not in self.chunks:
            chunk = self._load_chunk(chunk_x, chunk_z)
            if not chunk:
                chunk = Chunk(self, chunk_x, chunk_z)
                chunk.generate()
            self.chunks[key] = chunk
        return self.chunks[key]

    def get_block(self, x: int, y: int, z: int) -> int:
        chunk_x = x // CHUNK_SIZE
        chunk_z = z // CHUNK_SIZE
        chunk = self.get_chunk(chunk_x, chunk_z)
        local_x = x % CHUNK_SIZE
        local_z = z % CHUNK_SIZE
        return chunk.get_block(local_x, y, local_z)

    def set_block(self, x: int, y: int, z: int, block_type: int) -> None:
        chunk_x = x // CHUNK_SIZE
        chunk_z = z // CHUNK_SIZE
        chunk = self.get_chunk(chunk_x, chunk_z)
        local_x = x % CHUNK_SIZE
        local_z = z % CHUNK_SIZE
        chunk.set_block(local_x, y, local_z, block_type)
        chunk.needs_remesh = True

    def save(self) -> None:
        os.makedirs(SAVE_DIR, exist_ok=True)
        for chunk in self.chunks.values():
            path = os.path.join(SAVE_DIR, f"chunk_{chunk.chunk_x}_{chunk.chunk_z}.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump(chunk.serialize(), file)

    def _load_chunk(self, chunk_x: int, chunk_z: int) -> Optional[Chunk]:
        path = os.path.join(SAVE_DIR, f"chunk_{chunk_x}_{chunk_z}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return Chunk.from_data(self, data)


class Player:
    def __init__(self, world: World) -> None:
        self.world = world
        self.position = [0.0, 80.0, 0.0]
        self.velocity = [0.0, 0.0, 0.0]
        self.rotation = [0.0, 0.0]
        self.speed = 6.0
        self.flying = False
        self.jump_speed = 8.0
        self.gravity = 20.0
        self.height = 1.8
        self.radius = 0.3
        self.hotbar_index = 0

    def get_block_pos(self) -> Tuple[int, int, int]:
        return (int(self.position[0]), int(self.position[1]), int(self.position[2]))

    def update(self, dt: float, keys: pyglet.window.key.KeyStateHandler) -> None:
        move_dir = [0.0, 0.0, 0.0]
        forward = keys[pyglet.window.key.W] - keys[pyglet.window.key.S]
        strafe = keys[pyglet.window.key.D] - keys[pyglet.window.key.A]

        yaw = math.radians(self.rotation[0])
        move_dir[0] = math.sin(yaw) * forward + math.cos(yaw) * strafe
        move_dir[2] = math.cos(yaw) * forward - math.sin(yaw) * strafe

        if keys[pyglet.window.key.LSHIFT]:
            move_dir[1] -= 1
        if keys[pyglet.window.key.SPACE]:
            move_dir[1] += 1 if self.flying else 0

        length = math.sqrt(sum(component ** 2 for component in move_dir))
        if length:
            move_dir = [component / length for component in move_dir]

        self.velocity[0] = move_dir[0] * self.speed
        self.velocity[2] = move_dir[2] * self.speed

        if self.flying:
            self.velocity[1] = move_dir[1] * self.speed
        else:
            self.velocity[1] -= self.gravity * dt
            if keys[pyglet.window.key.SPACE] and self._on_ground():
                self.velocity[1] = self.jump_speed

        self._move(dt)

    def _on_ground(self) -> bool:
        x, y, z = self.position
        return self._collides(x, y - 0.05, z)

    def _move(self, dt: float) -> None:
        for axis in range(3):
            self.position[axis] += self.velocity[axis] * dt
            if self._collides(*self.position):
                self.position[axis] -= self.velocity[axis] * dt
                self.velocity[axis] = 0

    def _collides(self, x: float, y: float, z: float) -> bool:
        min_x = int(math.floor(x - self.radius))
        max_x = int(math.floor(x + self.radius))
        min_y = int(math.floor(y))
        max_y = int(math.floor(y + self.height))
        min_z = int(math.floor(z - self.radius))
        max_z = int(math.floor(z + self.radius))

        for cx in range(min_x, max_x + 1):
            for cy in range(min_y, max_y + 1):
                for cz in range(min_z, max_z + 1):
                    if self.world.get_block(cx, cy, cz) != BLOCK_AIR:
                        return True
        return False


class GameWindow(pyglet.window.Window):
    def __init__(self) -> None:
        super().__init__(1280, 720, "Voxel Engine MVP", resizable=True)
        self.set_exclusive_mouse(True)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        self.batch = pyglet.graphics.Batch()
        self.world = World(seed=42)
        self.texture_handler = TextureHandler(TEXTURE_FILE)
        self.player = Player(self.world)
        self.keys = pyglet.window.key.KeyStateHandler()
        self.push_handlers(self.keys)
        self.visible_chunks: Dict[Tuple[int, int], Chunk] = {}
        self.frustum_range = 4
        self._mouse_sensitivity = 0.15

        pyglet.clock.schedule_interval(self.update, 1 / 60)

    def on_draw(self) -> None:
        self.clear()
        self._setup_camera()
        self._update_visible_chunks()
        self.texture_handler.texture.bind()
        self.batch.draw()

    def on_resize(self, width: int, height: int) -> None:
        glViewport(0, 0, width, height)
        return super().on_resize(width, height)

    def update(self, dt: float) -> None:
        if self.keys[pyglet.window.key.ESCAPE]:
            self.close()
        if self.keys[pyglet.window.key.F]:
            self.player.flying = True
        if self.keys[pyglet.window.key.G]:
            self.player.flying = False

        self.player.update(dt, self.keys)
        for chunk in self.visible_chunks.values():
            if chunk.needs_remesh:
                chunk.rebuild_mesh(self.batch, self.texture_handler)

    def _update_visible_chunks(self) -> None:
        player_chunk_x = int(self.player.position[0]) // CHUNK_SIZE
        player_chunk_z = int(self.player.position[2]) // CHUNK_SIZE
        for dx in range(-self.frustum_range, self.frustum_range + 1):
            for dz in range(-self.frustum_range, self.frustum_range + 1):
                chunk = self.world.get_chunk(player_chunk_x + dx, player_chunk_z + dz)
                self.visible_chunks[(chunk.chunk_x, chunk.chunk_z)] = chunk

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        self.player.rotation[0] += dx * self._mouse_sensitivity
        self.player.rotation[1] = max(-89.9, min(89.9, self.player.rotation[1] - dy * self._mouse_sensitivity))

    def _setup_camera(self) -> None:
        width, height = self.get_framebuffer_size()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(70.0, width / max(height, 1), 0.1, 1000.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glRotatef(self.player.rotation[1], 1, 0, 0)
        glRotatef(-self.player.rotation[0], 0, 1, 0)
        glTranslatef(-self.player.position[0], -self.player.position[1], -self.player.position[2])

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol in (pyglet.window.key._1, pyglet.window.key._2, pyglet.window.key._3, pyglet.window.key._4):
            self.player.hotbar_index = symbol - pyglet.window.key._1
        if symbol == pyglet.window.key.P:
            self.world.save()

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        hit = self._raycast()
        if not hit:
            return
        block_pos, normal = hit
        if button == pyglet.window.mouse.LEFT:
            self.world.set_block(*block_pos, BLOCK_AIR)
        elif button == pyglet.window.mouse.RIGHT:
            target = (block_pos[0] + normal[0], block_pos[1] + normal[1], block_pos[2] + normal[2])
            block_type = BLOCK_TYPES[self.player.hotbar_index]
            self.world.set_block(*target, block_type)

    def _raycast(self) -> Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
        x, y, z = self.player.position
        yaw = math.radians(self.player.rotation[0])
        pitch = math.radians(self.player.rotation[1])
        direction = (
            math.cos(pitch) * math.sin(yaw),
            math.sin(pitch),
            math.cos(pitch) * math.cos(yaw),
        )
        for step in range(1, 80):
            distance = step * 0.2
            bx = int(x + direction[0] * distance)
            by = int(y + direction[1] * distance)
            bz = int(z + direction[2] * distance)
            if self.world.get_block(bx, by, bz) != BLOCK_AIR:
                nx = int(x + direction[0] * (distance - 0.2))
                ny = int(y + direction[1] * (distance - 0.2))
                nz = int(z + direction[2] * (distance - 0.2))
                normal = (bx - nx, by - ny, bz - nz)
                return (bx, by, bz), normal
        return None


if __name__ == "__main__":
    window = GameWindow()
    pyglet.app.run()
