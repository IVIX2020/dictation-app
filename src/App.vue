<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import * as OpenCC from 'opencc-js'

// --- ROUTING / STATE ---
const lessons = ref([])
const currentLessonId = ref(null)
const currentLessonMetadata = ref(null)
const currentLessonSegments = ref([])
const currentSegmentId = ref(0)
const progressData = ref(null)

const audioSrc = ref('')
const errorMessage = ref('')
const loadingDetail = ref(false)

// Audio controls
const audioPlayer = ref(null)
const playing = ref(false)
const currentTime = ref(0)
const stopTime = ref(-1)
const playSpeed = ref(1.0)
const masked = ref(true)
const keepShowing = ref(false)
const simplified = ref(false)

// Touch & Gesture state
const touchStartX = ref(0)
const touchStartY = ref(0)

// Double / Triple click handlers
const lastClickTimeOn = ref({ time: 0, element: '' })
const lastDoubleClickTimeOn = ref({ time: 0, element: '' })
const lastClickTime = ref(0)
const lastDoubleClickTime = ref(0)
const doubleClickTime = 300
const tripleClickTime = 300
let doubleClickTimeout = null

// Constants
const gapThreshold = 0.1
const errorSegmentThreshold = 5.0

// --- PROGRESS MANAGEMENT (localStorage) ---
const PROGRESS_KEY_PREFIX = 'dictation_progress_'

function loadProgress(lessonId) {
  const saved = localStorage.getItem(PROGRESS_KEY_PREFIX + lessonId)
  if (saved) {
    try {
      return JSON.parse(saved)
    } catch (e) {
      console.error('Error parsing progress', e)
    }
  }
  return {
    currentSegmentId: 0,
    segments: {}
  }
}

function saveProgress(lessonId, data) {
  localStorage.setItem(PROGRESS_KEY_PREFIX + lessonId, JSON.stringify(data))
}

function saveCurrentProgress() {
  if (!currentLessonId.value) return
  
  const segmentsProg = {}
  currentLessonSegments.value.forEach((seg, idx) => {
    const markedWords = []
    if (seg.words) {
      seg.words.forEach((w, wIdx) => {
        if (w.marked) markedWords.push(wIdx)
      })
    }
    segmentsProg[idx] = {
      studied: seg.studied || false,
      bookmarked: seg.bookmarked || false,
      markedWords
    }
  })
  
  progressData.value = {
    currentSegmentId: currentSegmentId.value,
    segments: segmentsProg
  }
  
  saveProgress(currentLessonId.value, progressData.value)
}

// --- LESSONS LOAD ---
async function loadLessons() {
  try {
    const res = await fetch('/dictation-app/lessons/lessons.json')
    if (!res.ok) {
      lessons.value = []
      return
    }
    const rawLessons = await res.json()
    
    lessons.value = await Promise.all(rawLessons.map(async (lesson) => {
      let segmentCount = 0
      try {
        const audioRes = await fetch(`/dictation-app/lessons/${lesson.id}/audio.json`)
        if (audioRes.ok) {
          const audioData = await audioRes.json()
          const rawSegs = audioData.segments || []
          const filteredSegs = filteredSegments(rawSegs, lesson.language)
          segmentCount = filteredSegs.length
        }
      } catch (e) {
        console.error(`Error loading segment count for ${lesson.id}`, e)
      }
      
      const prog = loadProgress(lesson.id)
      let studiedCount = 0
      let bookmarkedCount = 0
      const segmentsSummary = []
      
      for (let i = 0; i < segmentCount; i++) {
        const segProg = prog.segments[i] || { studied: false, bookmarked: false }
        if (segProg.studied) studiedCount++
        if (segProg.bookmarked) bookmarkedCount++
        segmentsSummary.push({
          studied: segProg.studied,
          bookmarked: segProg.bookmarked
        })
      }
      
      return {
        ...lesson,
        segmentCount,
        studiedCount,
        bookmarkedCount,
        segmentsSummary
      }
    }))
  } catch (error) {
    console.error('Failed to load lessons list:', error)
  }
}

async function loadLessonDetail(lessonId) {
  loadingDetail.value = true
  errorMessage.value = ''
  try {
    const metaRes = await fetch(`/dictation-app/lessons/${lessonId}/metadata.json`)
    if (!metaRes.ok) throw new Error('Metadata not found')
    currentLessonMetadata.value = await metaRes.json()
    
    const audioRes = await fetch(`/dictation-app/lessons/${lessonId}/audio.json`)
    if (!audioRes.ok) throw new Error('Transcription file not found')
    const audioData = await audioRes.json()
    
    audioSrc.value = `/dictation-app/lessons/${lessonId}/audio.mp3`
    
    progressData.value = loadProgress(lessonId)
    currentSegmentId.value = progressData.value.currentSegmentId || 0
    
    const rawSegments = audioData.segments || []
    const lang = currentLessonMetadata.value?.language || 'en'
    currentLessonSegments.value = filteredSegments(rawSegments, lang)
    
    currentLessonSegments.value.forEach((seg, idx) => {
      const segProg = progressData.value.segments[idx] || { studied: false, bookmarked: false, markedWords: [] }
      seg.studied = segProg.studied
      seg.bookmarked = segProg.bookmarked
      if (seg.words) {
        seg.words.forEach((w, wIdx) => {
          w.marked = segProg.markedWords && segProg.markedWords.includes(wIdx)
        })
      }
    })
    
    if (audioPlayer.value) {
      audioPlayer.value.src = audioSrc.value
      audioPlayer.value.load()
    }
  } catch (err) {
    console.error('Error loading detail:', err)
    errorMessage.value = err.message
  } finally {
    loadingDetail.value = false
  }
}

// --- ROUTING TRIGGERS ---
function updateRoute() {
  const params = new URLSearchParams(window.location.search)
  const id = params.get('id')
  if (id) {
    currentLessonId.value = id
    loadLessonDetail(id)
  } else {
    currentLessonId.value = null
    currentLessonMetadata.value = null
    currentLessonSegments.value = []
    loadLessons()
  }
}

function openLesson(lessonId) {
  window.history.pushState(null, '', `?id=${lessonId}`)
  updateRoute()
}

function goBackPage() {
  window.history.pushState(null, '', window.location.pathname)
  updateRoute()
}

onMounted(() => {
  updateRoute()
  window.addEventListener('popstate', updateRoute)
})

onBeforeUnmount(() => {
  window.removeEventListener('popstate', updateRoute)
})

// --- TIMING / SPLITTING UTILS ---
function getSegmentStart(seg) { return seg?.words[0]?.start ?? seg?.start ?? 0 }
function getSegmentEnd(seg) { return seg?.words.at(-1)?.end ?? seg?.end ?? 0 }
function getSegmentDuration(seg) { return getSegmentEnd(seg) - getSegmentStart(seg) }

function prepareSegmentWords(segment, language) {
  if (segment.words && segment.words.length > 0) return segment.words
  
  const text = segment.text || ''
  const segStart = segment.start || 0
  const segEnd = segment.end || 0
  const duration = segEnd - segStart
  
  let tokens = []
  const isCJK = ['zh', 'ja', 'ko'].includes(language)
  
  if (isCJK) {
    tokens = [...text.trim()]
  } else {
    tokens = text.trim().split(/\s+/).filter(Boolean)
  }
  
  if (tokens.length === 0) {
    return [{ word: text, start: segStart, end: segEnd }]
  }
  
  const step = duration / tokens.length
  return tokens.map((token, index) => ({
    word: token,
    start: segStart + index * step,
    end: segStart + (index + 1) * step
  }))
}

function filteredSegments(segments, language) {
  if (!segments) return []
  const processed = segments.map(s => ({
    ...s,
    words: prepareSegmentWords(s, language)
  }))
  return processed.flatMap(s => splitSegmentByGapRecursive(s, gapThreshold, errorSegmentThreshold))
}

function splitSegmentByGapRecursive(segment, gapThreshold, maxLength) {
  let segments = splitSegment(segment, gapThreshold)
  while (segments.some(s => getSegmentDuration(s) > maxLength)) {
    const temp = segments.flatMap(s =>
      getSegmentDuration(s) > maxLength ? splitSegment(s, gapThreshold) : s
    )
    if (temp.length === segments.length) break
    segments = temp
  }
  return segments
}

function splitSegment(segment, gapThreshold) {
  const segments = []
  const words = segment.words || []
  let currentWords = []
  let currentStart = getSegmentStart(segment)

  for (let i = 0; i < words.length; i++) {
    const word = words[i]
    currentWords.push(word)
    const nextStart = words[i + 1]?.start ?? word.end
    if (nextStart - word.end >= gapThreshold) {
      segments.push({
        ...segment,
        words: currentWords,
        start: currentStart,
        end: word.end
      })
      currentWords = []
      currentStart = nextStart
    }
  }
  if (currentWords.length) {
    segments.push({
      ...segment,
      words: currentWords,
      start: currentStart,
      end: words.at(-1)?.end ?? segment.end
    })
  }
  return segments
}

// --- COMPUTED PROPERTIES ---
const getCurrentSegment = computed(() => {
  return currentLessonSegments.value?.[currentSegmentId.value] || null
})

const currentProgressPercent = computed(() => {
  if (!currentLessonSegments.value || currentLessonSegments.value.length === 0) return 0
  return Math.round(((currentSegmentId.value + 1) / currentLessonSegments.value.length) * 100)
})

// Chinese traditional / simplified converter
const converterZh = OpenCC.Converter({ from: 'hk', to: 'cn' })

function filteredWords(words) {
  if (!words) return []
  if (currentLessonMetadata.value?.language === 'zh' && simplified.value) {
    return words.map(w => ({
      ...w,
      word: converterZh(w.word)
    }))
  }
  return words
}

function isHighlighted(word) {
  if (!playing.value) return false
  return currentTime.value >= word.start && currentTime.value < word.end
}

function getMaskedWord(word) {
  if (!word) return ''
  // Return clean bullet dots for masking
  return '•'.repeat(Math.max(word.length, 2))
}

// --- AUDIO PLAYER & TIMING ---
function playFrom(start, end) {
  if (!audioPlayer.value) return
  stopTime.value = end
  audioPlayer.value.currentTime = start
  audioPlayer.value.playbackRate = playSpeed.value
  audioPlayer.value.play().then(() => {
    playing.value = true
  }).catch(e => console.error('Play error', e))
}

function onTimeUpdate() {
  if (!audioPlayer.value) return
  currentTime.value = audioPlayer.value.currentTime
  if (stopTime.value > 0 && currentTime.value >= stopTime.value) {
    audioPlayer.value.pause()
    playing.value = false
    stopTime.value = -1
    
    // Mark studied
    const seg = currentLessonSegments.value?.[currentSegmentId.value]
    if (seg && !seg.studied) {
      seg.studied = true
      saveCurrentProgress()
    }
  }
}

function onPause() { playing.value = false }
function onPlay() { playing.value = true }
function onEnded() { playing.value = false }

watch(playSpeed, (newSpeed) => {
  if (audioPlayer.value) {
    audioPlayer.value.playbackRate = newSpeed
  }
})

watch(currentSegmentId, () => {
  if (playing.value && audioPlayer.value) {
    const seg = getCurrentSegment.value
    if (seg) playFrom(getSegmentStart(seg), getSegmentEnd(seg))
  }
})

// --- MOUSE & TOUCH GESTURES ---
function handleMouseDown(event, segment) {
  const rect = event.currentTarget.getBoundingClientRect()
  const clickX = event.clientX - rect.left
  const isLeft = clickX < rect.width / 2
  const currTime = Date.now()

  if (currTime - lastDoubleClickTime.value < tripleClickTime) {
    clearTimeout(doubleClickTimeout)
    handleTripleClick(isLeft)
  } else if (currTime - lastClickTime.value < doubleClickTime) {
    lastDoubleClickTime.value = currTime
    doubleClickTimeout = setTimeout(() => {
      handleDoubleClick(isLeft)
    }, tripleClickTime)
  } else {
    handleTap(segment)
  }

  lastClickTime.value = currTime
}

function handleTouchStart(event, segment) {
  event.preventDefault()
  const touch = event.touches[0]
  touchStartX.value = touch.clientX
  touchStartY.value = touch.clientY
  const rect = event.currentTarget.getBoundingClientRect()
  const clickX = touch.clientX - rect.left
  const isLeft = clickX < rect.width / 2
  const currTime = Date.now()

  if (currTime - lastDoubleClickTime.value < tripleClickTime) {
    clearTimeout(doubleClickTimeout)
    handleTripleClick(isLeft)
  } else if (currTime - lastClickTime.value < doubleClickTime) {
    lastDoubleClickTime.value = currTime
    doubleClickTimeout = setTimeout(() => {
      handleDoubleClick(isLeft)
    }, tripleClickTime)
  } else {
    handleTap(segment)
  }

  lastClickTime.value = currTime
}

function handleTouchEnd(event) {
  if (!event.changedTouches || event.changedTouches.length === 0) return
  const touchEnd = event.changedTouches[0]
  const diffX = touchEnd.clientX - touchStartX.value
  const diffY = touchEnd.clientY - touchStartY.value
  const minSwipeDistance = 40

  if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > minSwipeDistance) {
    if (diffX < 0) {
      getNextSegment()
    } else {
      getPreviousSegment()
    }
  }
}

function togglePlayCurrentSegment() {
  const seg = currentLessonSegments.value?.[currentSegmentId.value]
  if (!seg) return
  if (playing.value) {
    audioPlayer.value?.pause()
    playing.value = false
  } else {
    playFrom(getSegmentStart(seg), getSegmentEnd(seg))
  }
}

function handleTap(segment) {
  if (!segment) return
  if (playing.value) {
    audioPlayer.value?.pause()
    playing.value = false
  } else {
    playFrom(getSegmentStart(segment), getSegmentEnd(segment))
  }
}

function handleDoubleClick(isLeft) {
  isLeft ? getPreviousSegment() : getNextSegment()
}

function handleTripleClick(isLeft) {
  isLeft ? getPreviousBookmarkedSegment() : getNextBookmarkedSegment()
}

function getPreviousSegment() {
  if (currentSegmentId.value > 0) {
    currentSegmentId.value--
    saveCurrentProgress()
  }
}

function getNextSegment() {
  if (currentSegmentId.value < currentLessonSegments.value.length - 1) {
    currentSegmentId.value++
    saveCurrentProgress()
  }
}

function getPreviousBookmarkedSegment() {
  for (let i = currentSegmentId.value - 1; i >= 0; i--) {
    if (currentLessonSegments.value[i].bookmarked) {
      currentSegmentId.value = i
      saveCurrentProgress()
      break
    }
  }
}

function getNextBookmarkedSegment() {
  for (let i = currentSegmentId.value + 1; i < currentLessonSegments.value.length; i++) {
    if (currentLessonSegments.value[i].bookmarked) {
      currentSegmentId.value = i
      saveCurrentProgress()
      break
    }
  }
}

function toggleBookmark() {
  const seg = currentLessonSegments.value?.[currentSegmentId.value]
  if (!seg) return
  seg.bookmarked = !seg.bookmarked
  saveCurrentProgress()
}

function handleMouseDownOnWord(event, word) {
  event.preventDefault()
  event.stopPropagation()
  const currTime = Date.now()
  
  if (currTime - lastDoubleClickTimeOn.value.time < doubleClickTime && lastDoubleClickTimeOn.value.element === 'word') {
    word.marked = !word.marked
    if (word.marked) {
      const seg = currentLessonSegments.value?.[currentSegmentId.value]
      if (seg) seg.bookmarked = true
    }
    saveCurrentProgress()
  } else if (currTime - lastClickTimeOn.value.time < doubleClickTime && lastClickTimeOn.value.element === 'word') {
    lastDoubleClickTimeOn.value = { time: currTime, element: 'word' }
  } else {
    const seg = currentLessonSegments.value?.[currentSegmentId.value]
    const segEnd = getSegmentEnd(seg)
    playFrom(word.start, segEnd)
    lastClickTimeOn.value = { time: currTime, element: 'word' }
  }
}

// Global Hide Trigger
function toggleGlobalHide(isVisible) {
  const now = Date.now()
  const last = lastClickTimeOn.value
  keepShowing.value = false
  if (now - last.time < doubleClickTime && last.element === 'hide' && isVisible) {
    keepShowing.value = true
    masked.value = false
  } else {
    masked.value = !isVisible
    lastClickTimeOn.value = { time: now, element: 'hide' }
  }
}
</script>

<template>
  <div class="app-container">
    <!-- --- MINIMAL HEADER --- -->
    <header class="app-header">
      <div class="header-inner">
        <div class="header-left">
          <button v-if="currentLessonId" class="minimal-back-btn" @click="goBackPage">
            <span class="icon">‹</span>
            <span>Lessons</span>
          </button>
          <div v-else class="brand-title">
            <span class="brand-badge">PRO</span>
            <span>Dictation</span>
          </div>
        </div>

        <div class="header-right" v-if="currentLessonId && currentLessonMetadata">
          <!-- Speed control pill -->
          <div class="speed-pill">
            <select v-model="playSpeed" class="speed-select-minimal">
              <option :value="0.7">0.7x</option>
              <option :value="0.8">0.8x</option>
              <option :value="1.0">1.0x</option>
              <option :value="1.2">1.2x</option>
              <option :value="1.5">1.5x</option>
            </select>
          </div>

          <button v-if="currentLessonMetadata.language === 'zh'" class="minimal-tag-btn" @click="simplified = !simplified">
            {{ simplified ? '簡' : '繁' }}
          </button>
        </div>
      </div>
    </header>

    <main class="app-main">
      <!-- --- ERROR BANNER --- -->
      <div v-if="errorMessage" class="minimal-error">
        <span>⚠️ {{ errorMessage }}</span>
      </div>

      <!-- --- SECTION 1: LESSONS LIST (MINIMAL DASHBOARD) --- -->
      <section v-if="!currentLessonId" class="lessons-section">
        <div class="section-header">
          <h1 class="page-title">My Materials</h1>
          <span class="count-badge" v-if="lessons.length > 0">{{ lessons.length }} lessons</span>
        </div>
        
        <div v-if="lessons.length === 0" class="minimal-empty-state">
          <div class="empty-icon">🎧</div>
          <h3>No Lessons Available</h3>
          <p>Generate new dictation materials via CLI:</p>
          <code>python tools/make_lesson.py &lt;URL&gt;</code>
        </div>

        <div v-else class="lessons-list">
          <div 
            v-for="lesson in lessons" 
            :key="lesson.id" 
            class="minimal-lesson-card" 
            @click="openLesson(lesson.id)"
          >
            <div class="card-top">
              <span class="lang-badge">{{ lesson.language.toUpperCase() }}</span>
              <span class="card-date">{{ lesson.createdAt.split(' ')[0] }}</span>
            </div>
            
            <h2 class="card-title">{{ lesson.title }}</h2>
            
            <div class="card-footer">
              <div class="progress-info">
                <span class="progress-text">{{ lesson.studiedCount }} / {{ lesson.segmentCount }} sentences</span>
                <span v-if="lesson.bookmarkedCount > 0" class="bookmark-badge">★ {{ lesson.bookmarkedCount }}</span>
              </div>

              <div class="mini-progress-track">
                <div 
                  class="mini-progress-fill" 
                  :style="{ width: `${Math.round((lesson.studiedCount / (lesson.segmentCount || 1)) * 100)}%` }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- --- SECTION 2: MOBILE DICTATION WORKSPACE (MINIMAL FOCUS) --- -->
      <section v-else class="dictation-focus-section">
        <div v-if="loadingDetail" class="minimal-loader">
          <div class="pulse-ring"></div>
          <span>Loading audio & transcript...</span>
        </div>

        <div v-else-if="currentLessonMetadata && currentLessonSegments.length > 0" class="focus-workspace">
          
          <!-- Sleek Top Progress & Meta -->
          <div class="workspace-top-bar">
            <div class="progress-meta">
              <span class="sentence-counter">Sentence <strong>{{ currentSegmentId + 1 }}</strong> / {{ currentLessonSegments.length }}</span>
              <span class="percent-tag">{{ currentProgressPercent }}%</span>
            </div>
            
            <!-- Thin Line Progress Bar -->
            <div class="top-progress-bar">
              <div class="progress-fill" :style="{ width: `${currentProgressPercent}%` }"></div>
            </div>
          </div>

          <!-- --- MAIN FOCUS DICTATION CANVAS --- -->
          <div class="focus-card-canvas">
            <div 
              class="canvas-touch-zone"
              @mousedown="handleMouseDown($event, getCurrentSegment)"
              @touchstart="handleTouchStart($event, getCurrentSegment)"
              @touchend="handleTouchEnd($event)"
            >
              <!-- Background Ambient Hint -->
              <div class="ambient-hint">
                <span class="hint-side">‹ Swipe</span>
                <span class="hint-center">Tap to play / pause</span>
                <span class="hint-side">Swipe ›</span>
              </div>

              <!-- Interactive Word Chips Display -->
              <div class="words-container">
                <div class="words-flex">
                  <span
                    v-for="(word, key) in filteredWords(getCurrentSegment?.words)"
                    :key="key"
                    class="focus-word-chip"
                    :class="{ 
                      'highlighted': isHighlighted(word), 
                      'marked': word.marked,
                      'is-masked': masked
                    }"
                    @mousedown="handleMouseDownOnWord($event, word)"
                    @touchstart="handleMouseDownOnWord($event, word)"
                  >
                    <span v-if="masked" class="masked-dots">{{ getMaskedWord(word.word) }}</span>
                    <span v-else class="revealed-text">{{ word.word }}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Hidden HTML5 Audio Element -->
          <audio 
            ref="audioPlayer" 
            :src="audioSrc" 
            @timeupdate="onTimeUpdate" 
            @pause="onPause" 
            @play="onPlay" 
            @ended="onEnded"
          ></audio>
        </div>
      </section>
    </main>

    <!-- --- MOBILE STICKY THUMB CONTROL BAR --- -->
    <div v-if="currentLessonId && currentLessonSegments.length > 0" class="bottom-sticky-bar">
      <div class="bottom-bar-content">
        <!-- Bookmark -->
        <button 
          class="thumb-btn bookmark-thumb-btn" 
          :class="{ active: currentLessonSegments[currentSegmentId]?.bookmarked }"
          @click="toggleBookmark"
          title="Bookmark sentence"
        >
          <span class="thumb-icon">★</span>
          <span class="thumb-label">Mark</span>
        </button>

        <!-- Previous -->
        <button class="thumb-btn nav-thumb-btn" @click="getPreviousSegment" title="Previous Sentence">
          <span class="thumb-icon">⏮</span>
          <span class="thumb-label">Prev</span>
        </button>

        <!-- Play / Pause -->
        <button class="thumb-btn play-thumb-btn" :class="{ playing: playing }" @click="togglePlayCurrentSegment" title="Play or Pause">
          <span class="thumb-icon">{{ playing ? '⏸' : '▶' }}</span>
          <span class="thumb-label">{{ playing ? 'Pause' : 'Play' }}</span>
        </button>

        <!-- Next -->
        <button class="thumb-btn nav-thumb-btn" @click="getNextSegment" title="Next Sentence">
          <span class="thumb-icon">⏭</span>
          <span class="thumb-label">Next</span>
        </button>

        <!-- Hold to Peek -->
        <button 
          class="thumb-btn peek-thumb-btn"
          :class="{ active: !masked || keepShowing }"
          @mousedown="toggleGlobalHide(true)"
          @mouseup="keepShowing ? null : toggleGlobalHide(false)"
          @mouseleave="keepShowing ? null : (masked = true)"
          @touchstart.prevent="toggleGlobalHide(true)"
          @touchend.prevent="keepShowing ? null : toggleGlobalHide(false)"
          title="Hold to Peek"
        >
          <span class="thumb-icon">👁️</span>
          <span class="thumb-label">Peek</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ==========================================================================
   MINIMAL MOBILE-FIRST DICTATION STYLES
   ========================================================================== */

.app-container {
  max-width: 640px;
  margin: 0 auto;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-main);
  position: relative;
}

/* MINIMAL HEADER */
.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(11, 15, 25, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--bg-card-border);
  padding: 0.75rem 1.25rem;
}

.header-inner {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.brand-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.brand-badge {
  font-size: 0.65rem;
  font-weight: 800;
  background: var(--accent);
  color: #fff;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  letter-spacing: 0.05em;
}

.minimal-back-btn {
  background: transparent;
  border: none;
  color: var(--accent-light);
  font-size: 0.95rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  cursor: pointer;
  padding: 0.2rem 0;
}

.minimal-back-btn .icon {
  font-size: 1.4rem;
  line-height: 1;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.speed-select-minimal {
  background: var(--bg-card);
  border: 1px solid var(--bg-card-border);
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.25rem 0.5rem;
  border-radius: 8px;
  outline: none;
  cursor: pointer;
}

.minimal-tag-btn {
  background: var(--bg-card);
  border: 1px solid var(--bg-card-border);
  color: var(--text-primary);
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.25rem 0.5rem;
  border-radius: 8px;
  cursor: pointer;
}

/* APP MAIN CONTAINER */
.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 1rem 1.25rem;
}

.minimal-error {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fca5a5;
  padding: 0.75rem 1rem;
  border-radius: 10px;
  font-size: 0.85rem;
  margin-bottom: 1rem;
}

/* LESSONS DASHBOARD */
.lessons-section {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--text-primary);
}

.count-badge {
  font-size: 0.8rem;
  color: var(--text-muted);
  font-weight: 500;
}

.minimal-empty-state {
  text-align: center;
  padding: 3rem 1.5rem;
  background: var(--bg-card);
  border: 1px dashed var(--bg-card-border);
  border-radius: 16px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 2.5rem;
  margin-bottom: 0.75rem;
}

.minimal-empty-state h3 {
  font-size: 1.1rem;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.minimal-empty-state code {
  display: inline-block;
  margin-top: 0.75rem;
  font-size: 0.8rem;
  color: var(--accent-light);
  background: rgba(99, 102, 241, 0.1);
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
}

.lessons-list {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.minimal-lesson-card {
  background: var(--bg-card);
  border: 1px solid var(--bg-card-border);
  border-radius: 16px;
  padding: 1.15rem;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease;
}

.minimal-lesson-card:active {
  transform: scale(0.98);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.lang-badge {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--accent-light);
  background: rgba(99, 102, 241, 0.15);
  padding: 0.15rem 0.5rem;
  border-radius: 6px;
}

.card-date {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.card-title {
  font-size: 1.1rem;
  font-weight: 600;
  line-height: 1.35;
  color: var(--text-primary);
  margin-bottom: 1rem;
}

.card-footer {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.bookmark-badge {
  color: var(--warning);
  font-weight: 600;
}

.mini-progress-track {
  height: 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
}

/* ==========================================================================
   MINIMAL DICTATION WORKSPACE
   ========================================================================== */

.dictation-focus-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.focus-workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 80px; /* space for fixed thumb bar */
}

/* TOP PROGRESS BAR */
.workspace-top-bar {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.25rem;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.sentence-counter strong {
  color: var(--text-primary);
}

.percent-tag {
  font-weight: 600;
  color: var(--accent-light);
}

.top-progress-bar {
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-light));
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

/* MAIN FOCUS CANVAS */
.focus-card-canvas {
  flex: 1;
  min-height: 280px;
  background: var(--bg-card);
  border: 1px solid var(--bg-card-border);
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
}

.canvas-touch-zone {
  width: 100%;
  height: 100%;
  min-height: 280px;
  padding: 2rem 1.25rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  cursor: pointer;
  user-select: none;
}

.ambient-hint {
  position: absolute;
  top: 0.75rem;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-between;
  padding: 0 1rem;
  font-size: 0.7rem;
  color: var(--text-muted);
  opacity: 0.4;
  pointer-events: none;
}

.words-container {
  width: 100%;
  display: flex;
  justify-content: center;
}

.words-flex {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 0.5rem;
  justify-content: center;
  align-items: center;
  max-width: 520px;
}

/* WORD CHIPS STYLE */
.focus-word-chip {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0.5rem 0.85rem;
  border-radius: 12px;
  font-size: 1.25rem;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
}

.focus-word-chip.is-masked {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.06);
}

.focus-word-chip:active {
  transform: scale(0.95);
}

/* HIGHLIGHTED WORD (VOICE TIMING) */
.focus-word-chip.highlighted {
  background: var(--accent);
  border-color: var(--accent-light);
  color: #ffffff;
  box-shadow: 0 0 20px var(--accent-glow);
  transform: scale(1.04);
}

.focus-word-chip.highlighted .masked-dots {
  color: rgba(255, 255, 255, 0.7);
}

/* MARKED WORD */
.focus-word-chip.marked {
  background: rgba(16, 185, 129, 0.15);
  border-color: rgba(16, 185, 129, 0.4);
  color: #34d399;
}

.masked-dots {
  letter-spacing: 0.15rem;
  color: #64748b;
  font-family: var(--mono);
}

.revealed-text {
  font-weight: 600;
}

/* MINIMAL LOADER */
.minimal-loader {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.pulse-ring {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 0 var(--accent-glow);
  animation: pulse-ring 1.25s infinite cubic-bezier(0.215, 0.61, 0.355, 1);
}

@keyframes pulse-ring {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 var(--accent-glow); }
  70% { transform: scale(1); box-shadow: 0 0 0 16px rgba(99, 102, 241, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
}

/* ==========================================================================
   FIXED BOTTOM THUMB CONTROL BAR
   ========================================================================== */

.bottom-sticky-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: rgba(11, 15, 25, 0.9);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid var(--bg-card-border);
  padding: 0.6rem 1rem calc(0.6rem + env(safe-area-inset-bottom, 0px));
}

.bottom-bar-content {
  max-width: 480px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.thumb-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--bg-card-border);
  border-radius: 16px;
  padding: 0.5rem 0.5rem;
  flex: 1;
  max-width: 68px;
  min-height: 56px;
  color: var(--text-primary);
  cursor: pointer;
  user-select: none;
  touch-action: manipulation;
  transition: transform 0.1s ease, background-color 0.15s ease;
}

.thumb-btn:active {
  transform: scale(0.92);
}

.thumb-icon {
  font-size: 1.25rem;
  line-height: 1;
}

.thumb-label {
  font-size: 0.68rem;
  font-weight: 600;
  margin-top: 4px;
  color: var(--text-muted);
}

.play-thumb-btn {
  background: var(--accent);
  border-color: var(--accent-light);
  color: white;
  min-height: 60px;
  box-shadow: 0 4px 14px var(--accent-glow);
}

.play-thumb-btn .thumb-label {
  color: white;
}

.play-thumb-btn.playing {
  background: #ef4444;
  border-color: #f87171;
  box-shadow: 0 4px 14px rgba(239, 68, 68, 0.35);
}

.bookmark-thumb-btn.active {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.4);
  color: var(--warning);
}

.bookmark-thumb-btn.active .thumb-label {
  color: var(--warning);
}

.peek-thumb-btn.active {
  background: rgba(99, 102, 241, 0.18);
  border-color: var(--accent-light);
  color: var(--accent-light);
}

.peek-thumb-btn.active .thumb-label {
  color: var(--accent-light);
}
</style>