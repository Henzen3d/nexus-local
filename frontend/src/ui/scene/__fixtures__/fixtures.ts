import type { SandboxBlock } from '../../../types'

export const orbitFixture: SandboxBlock = {
  id: 'scene_orbit',
  type: 'sandbox',
  kind: 'scene',
  mode: '3d',
  title: 'Órbita Planetária',
  params: [
    { id: 'velocidade', label: 'Velocidade orbital', kind: 'range', min: 0.2, max: 3, step: 0.1, default: 1 },
  ],
  readout: [
    { key: 'angulo', label: 'Ângulo', unit: 'rad' },
    { key: 'raio', label: 'Raio', unit: 'ua' },
  ],
  code: `const sunGeo = new THREE.SphereGeometry(1.2, 24, 24);
const sunMat = new THREE.MeshBasicMaterial({ color: 0xffaa00 });
const sun = new THREE.Mesh(sunGeo, sunMat);
scene.add(sun);
const planetGeo = new THREE.SphereGeometry(0.5, 16, 16);
const planetMat = new THREE.MeshStandardMaterial({ color: 0x44aaff, roughness: 0.4 });
const planet = new THREE.Mesh(planetGeo, planetMat);
scene.add(planet);
const orbitR = 5;
let theta = 0;
camera.position.set(0, 8, 10);
camera.lookAt(0, 0, 0);
onFrame((t, dt) => {
  const speed = Number(params.velocidade || 1);
  theta += speed * dt;
  planet.position.x = Math.cos(theta) * orbitR;
  planet.position.z = Math.sin(theta) * orbitR;
  report({ angulo: Math.round((theta % (2 * Math.PI)) * 100) / 100, raio: orbitR });
});`,
}

export const pendulumFixture: SandboxBlock = {
  id: 'scene_pendulum',
  type: 'sandbox',
  kind: 'scene',
  mode: '2d',
  title: 'Pêndulo Simples',
  params: [
    { id: 'comprimento', label: 'Comprimento', kind: 'range', min: 100, max: 300, step: 10, default: 200 },
    { id: 'gravidade', label: 'Gravidade', kind: 'range', min: 1, max: 20, step: 1, default: 9.8 },
  ],
  readout: [
    { key: 'angulo', label: 'Ângulo', unit: '°' },
    { key: 'periodo', label: 'Período', unit: 's' },
  ],
  code: `let angle = Math.PI / 4;
let aVel = 0;
const originX = 400;
const originY = 50;
onFrame((t, dt) => {
  const len = Number(params.comprimento || 200);
  const g = Number(params.gravidade || 9.8);
  const aAcc = (-1 * (g * 10) / len) * Math.sin(angle);
  aVel += aAcc * dt;
  angle += aVel * dt;
  aVel *= 0.999;
  const bobX = originX + len * Math.sin(angle);
  const bobY = originY + len * Math.cos(angle);
  ctx.strokeStyle = theme.text;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(originX, originY);
  ctx.lineTo(bobX, bobY);
  ctx.stroke();
  ctx.fillStyle = theme.accent;
  ctx.beginPath();
  ctx.arc(bobX, bobY, 18, 0, Math.PI * 2);
  ctx.fill();
  const deg = Math.round((angle * 180 / Math.PI) * 10) / 10;
  const period = Math.round((2 * Math.PI * Math.sqrt(len / (g * 10))) * 100) / 100;
  report({ angulo: deg, periodo: period });
});`,
}

export const bubbleSortFixture: SandboxBlock = {
  id: 'scene_bubblesort',
  type: 'sandbox',
  kind: 'scene',
  mode: '2d',
  title: 'Ordenação Bubble Sort',
  params: [
    {
      id: 'n',
      label: 'Elementos',
      kind: 'select',
      default: '20',
      options: [
        { value: '10', label: '10' },
        { value: '20', label: '20' },
        { value: '30', label: '30' },
      ],
    },
  ],
  readout: [
    { key: 'comparacoes', label: 'Comparações' },
    { key: 'trocas', label: 'Trocas' },
  ],
  code: `let arr = [];
let i = 0, j = 0, comps = 0, swaps = 0;
function resetArr(n) {
  arr = Array.from({ length: n }, () => Math.floor(Math.random() * 300) + 20);
  i = 0; j = 0; comps = 0; swaps = 0;
}
resetArr(Number(params.n || 20));
let lastN = params.n;
let stepTimer = 0;
onFrame((t, dt) => {
  if (params.n !== lastN) { lastN = params.n; resetArr(Number(lastN)); }
  stepTimer += dt;
  if (stepTimer > 0.05 && i < arr.length) {
    stepTimer = 0;
    comps++;
    if (arr[j] > arr[j + 1]) {
      const tmp = arr[j]; arr[j] = arr[j + 1]; arr[j + 1] = tmp;
      swaps++;
    }
    j++;
    if (j >= arr.length - i - 1) { j = 0; i++; }
    report({ comparacoes: comps, trocas: swaps });
  }
  const barW = (800 - 40) / arr.length;
  for (let k = 0; k < arr.length; k++) {
    ctx.fillStyle = k === j ? theme.accent : (k > arr.length - i - 1 ? '#5db872' : theme.text);
    ctx.fillRect(20 + k * barW, 400 - arr[k], barW - 2, arr[k]);
  }
});`,
}

export const particlesFixture: SandboxBlock = {
  id: 'scene_particles',
  type: 'sandbox',
  kind: 'scene',
  mode: '3d',
  title: 'Enxame de Partículas',
  params: [
    { id: 'atrito', label: 'Atrito', kind: 'range', min: 0.85, max: 0.99, step: 0.01, default: 0.95 },
  ],
  readout: [
    { key: 'particulas', label: 'Partículas' },
    { key: 'energia', label: 'Energia Cinética' },
  ],
  code: `const count = 200;
const geom = new THREE.BufferGeometry();
const pos = new Float32Array(count * 3);
const vel = new Float32Array(count * 3);
for (let i = 0; i < count; i++) {
  pos[i * 3] = (Math.random() - 0.5) * 10;
  pos[i * 3 + 1] = (Math.random() - 0.5) * 10;
  pos[i * 3 + 2] = (Math.random() - 0.5) * 10;
  vel[i * 3] = (Math.random() - 0.5) * 2;
  vel[i * 3 + 1] = (Math.random() - 0.5) * 2;
  vel[i * 3 + 2] = (Math.random() - 0.5) * 2;
}
geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
const mat = new THREE.PointsMaterial({ color: 0x5db8a6, size: 0.25 });
const cloud = new THREE.Points(geom, mat);
scene.add(cloud);
camera.position.set(0, 0, 15);
onFrame((t, dt) => {
  const friction = Number(params.atrito || 0.95);
  const arr = geom.attributes.position.array;
  let kinetic = 0;
  for (let i = 0; i < count; i++) {
    vel[i * 3] += (Math.random() - 0.5) * 0.1;
    vel[i * 3] *= Math.pow(friction, dt * 60);
    arr[i * 3] += vel[i * 3] * dt * 5;
    arr[i * 3 + 1] += vel[i * 3 + 1] * dt * 5;
    arr[i * 3 + 2] += vel[i * 3 + 2] * dt * 5;
    kinetic += vel[i * 3] ** 2 + vel[i * 3 + 1] ** 2;
  }
  geom.attributes.position.needsUpdate = true;
  report({ particulas: count, energia: Math.round(kinetic * 10) / 10 });
});`,
}

export const surfaceFixture: SandboxBlock = {
  id: 'scene_surface',
  type: 'sandbox',
  kind: 'scene',
  mode: '3d',
  title: 'Gráfico de Superfície 3D',
  params: [
    { id: 'amplitude', label: 'Amplitude', kind: 'range', min: 0.5, max: 3, step: 0.25, default: 1.5 },
  ],
  readout: [
    { key: 'pico_z', label: 'Pico Z', unit: 'm' },
  ],
  code: `const size = 30;
const geo = new THREE.PlaneGeometry(10, 10, size, size);
geo.rotateX(-Math.PI / 2);
const mat = new THREE.MeshStandardMaterial({ color: 0xcc785c, wireframe: true });
const mesh = new THREE.Mesh(geo, mat);
scene.add(mesh);
camera.position.set(8, 8, 10);
camera.lookAt(0, 0, 0);
onFrame((t, dt) => {
  const amp = Number(params.amplitude || 1.5);
  const pos = geo.attributes.position;
  let maxZ = 0;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    const y = Math.sin(x * 0.8 + t * 2) * Math.cos(z * 0.8 + t * 2) * amp;
    pos.setY(i, y);
    if (Math.abs(y) > maxZ) maxZ = Math.abs(y);
  }
  pos.needsUpdate = true;
  report({ pico_z: Math.round(maxZ * 100) / 100 });
});`,
}

export const clockFixture: SandboxBlock = {
  id: 'scene_clock',
  type: 'sandbox',
  kind: 'scene',
  mode: '2d',
  title: 'Relógio Analógico',
  params: [
    { id: 'velocidade', label: 'Multiplicador de tempo', kind: 'range', min: 1, max: 60, step: 1, default: 1 },
  ],
  readout: [
    { key: 'hora', label: 'Horário' },
  ],
  code: `let simTime = Date.now();
onFrame((t, dt) => {
  const speed = Number(params.velocidade || 1);
  simTime += dt * 1000 * speed;
  const d = new Date(simTime);
  const hrs = d.getHours() % 12;
  const mins = d.getMinutes();
  const secs = d.getSeconds() + d.getMilliseconds() / 1000;
  const cx = 400, cy = 225, r = 160;
  ctx.strokeStyle = theme.text;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();
  function drawHand(angle, len, width, color) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle - Math.PI / 2) * len, cy + Math.sin(angle - Math.PI / 2) * len);
    ctx.stroke();
  }
  drawHand((hrs + mins / 60) * (Math.PI / 6), r * 0.5, 6, theme.text);
  drawHand(mins * (Math.PI / 30), r * 0.75, 4, theme.text);
  drawHand(secs * (Math.PI / 30), r * 0.85, 2, theme.accent);
  const pad = (n) => String(Math.floor(n)).padStart(2, '0');
  report({ hora: \`\${pad(d.getHours())}:\${pad(mins)}:\${pad(secs)}\` });
});`,
}

export const ALL_CANONICAL_SCENES = [
  orbitFixture,
  pendulumFixture,
  bubbleSortFixture,
  particlesFixture,
  surfaceFixture,
  clockFixture,
]
