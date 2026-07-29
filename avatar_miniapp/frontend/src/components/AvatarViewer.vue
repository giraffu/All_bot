<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'

import type { AnimationId, BackgroundId, CameraPreset } from '@/types'

const props = withDefaults(
  defineProps<{
    modelUrl: string | null
    animationId: AnimationId
    playing: boolean
    speed: number
    loop: boolean
    cameraPreset: CameraPreset
    background: BackgroundId
  }>(),
  {
    modelUrl: null,
    animationId: 'idle',
    playing: true,
    speed: 1,
    loop: true,
    cameraPreset: 'full_body',
    background: 'studio',
  },
)

const emit = defineEmits<{
  loaded: [animations: string[]]
  progress: [ratio: number]
  error: [message: string]
}>()

const root = ref<HTMLDivElement | null>(null)
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let mixer: THREE.AnimationMixer | null = null
let currentAction: THREE.AnimationAction | null = null
let modelRoot: THREE.Object3D | null = null
let clock: THREE.Clock | null = null
let animationFrame = 0
let resizeObserver: ResizeObserver | null = null
const clips = new Map<string, THREE.AnimationClip>()

const cameraPresets: Record<CameraPreset, { position: [number, number, number]; target: [number, number, number] }> = {
  front: { position: [0, 1.15, 4.3], target: [0, 1, 0] },
  side: { position: [4.3, 1.15, 0], target: [0, 1, 0] },
  back: { position: [0, 1.15, -4.3], target: [0, 1, 0] },
  full_body: { position: [2.5, 1.35, 3.3], target: [0, 1, 0] },
  half_body: { position: [1.5, 1.55, 2.4], target: [0, 1.35, 0] },
  portrait: { position: [0.75, 1.68, 1.7], target: [0, 1.62, 0] },
}

const backgrounds: Record<Exclude<BackgroundId, 'transparent'>, number> = {
  light: 0xdbe7f5,
  dark: 0x080d18,
  studio: 0x111d2e,
}

function applyCamera() {
  if (!camera || !controls) return
  const preset = cameraPresets[props.cameraPreset]
  camera.position.set(...preset.position)
  controls.target.set(...preset.target)
  controls.update()
}

function applyBackground() {
  if (!scene || !renderer) return
  if (props.background === 'transparent') {
    scene.background = null
    renderer.setClearColor(0x000000, 0)
  } else {
    scene.background = new THREE.Color(backgrounds[props.background])
    renderer.setClearColor(backgrounds[props.background], 1)
  }
}

function playSelectedClip() {
  if (!mixer) return
  currentAction?.fadeOut(0.18)
  const clip = clips.get(props.animationId) || clips.values().next().value
  if (!clip) return
  const action = mixer.clipAction(clip)
  action.reset()
  action.enabled = true
  action.setLoop(props.loop ? THREE.LoopRepeat : THREE.LoopOnce, props.loop ? Infinity : 1)
  action.clampWhenFinished = !props.loop
  action.timeScale = props.speed
  action.fadeIn(0.18).play()
  currentAction = action
  if (!props.playing) action.paused = true
}

function disposeModel() {
  if (!modelRoot || !scene) return
  scene.remove(modelRoot)
  modelRoot.traverse((object) => {
    const mesh = object as THREE.Mesh
    mesh.geometry?.dispose()
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    materials.filter(Boolean).forEach((material) => material.dispose())
  })
  modelRoot = null
  mixer = null
  currentAction = null
  clips.clear()
}

async function loadModel() {
  disposeModel()
  if (!props.modelUrl || !scene) return
  const loader = new GLTFLoader()
  loader.register((parser) => new VRMLoaderPlugin(parser))
  try {
    const gltf = await loader.loadAsync(props.modelUrl)
    const vrm = gltf.userData.vrm
    if (vrm) {
      VRMUtils.removeUnnecessaryVertices(gltf.scene)
      VRMUtils.rotateVRM0(vrm)
    }
    modelRoot = gltf.scene
    scene.add(modelRoot)
    mixer = new THREE.AnimationMixer(modelRoot)
    gltf.animations.forEach((clip) => clips.set(clip.name, clip))
    emit('loaded', [...clips.keys()])
    playSelectedClip()
  } catch (error) {
    emit('error', error instanceof Error ? error.message : 'MODEL_LOAD_FAILED')
  }
}

function resize() {
  if (!root.value || !renderer || !camera) return
  const width = root.value.clientWidth
  const height = root.value.clientHeight
  renderer.setSize(width, height, false)
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
  camera.aspect = width / Math.max(height, 1)
  camera.updateProjectionMatrix()
}

function animate() {
  animationFrame = requestAnimationFrame(animate)
  const delta = clock?.getDelta() || 0
  if (mixer && props.playing) {
    mixer.update(delta)
    if (currentAction) {
      const duration = currentAction.getClip().duration || 1
      emit('progress', (currentAction.time % duration) / duration)
    }
  }
  controls?.update()
  if (renderer && scene && camera) renderer.render(scene, camera)
}

function screenshot() {
  if (!renderer || !scene || !camera) return
  renderer.render(scene, camera)
  const link = document.createElement('a')
  link.download = `avatar-${Date.now()}.png`
  link.href = renderer.domElement.toDataURL('image/png')
  link.click()
}

defineExpose({ screenshot })

watch(() => props.modelUrl, loadModel)
watch(() => props.animationId, playSelectedClip)
watch(() => props.loop, playSelectedClip)
watch(() => props.speed, (speed) => {
  if (currentAction) currentAction.timeScale = speed
})
watch(() => props.playing, (playing) => {
  if (currentAction) currentAction.paused = !playing
})
watch(() => props.cameraPreset, applyCamera)
watch(() => props.background, applyBackground)

onMounted(() => {
  if (!root.value) return
  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(38, 1, 0.05, 100)
  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  })
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05
  root.value.appendChild(renderer.domElement)
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.minDistance = 0.8
  controls.maxDistance = 8
  scene.add(new THREE.HemisphereLight(0xffffff, 0x203050, 2.2))
  const key = new THREE.DirectionalLight(0xffffff, 3.2)
  key.position.set(3, 4, 4)
  scene.add(key)
  const rim = new THREE.DirectionalLight(0x5ad8ff, 1.8)
  rim.position.set(-3, 2, -2)
  scene.add(rim)
  const grid = new THREE.GridHelper(8, 16, 0x3d7896, 0x23384b)
  scene.add(grid)
  clock = new THREE.Clock()
  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(root.value)
  applyCamera()
  applyBackground()
  void loadModel()
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  disposeModel()
  controls?.dispose()
  renderer?.dispose()
  renderer?.domElement.remove()
})
</script>

<template>
  <div ref="root" class="avatar-viewer" aria-label="3D avatar viewer">
    <div v-if="!modelUrl" class="viewer-placeholder">
      <div class="viewer-orbit" />
      <slot />
    </div>
  </div>
</template>
