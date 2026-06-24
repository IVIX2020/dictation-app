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

// Double / Triple click handlers
const lastClickTimeOn = ref({ time: 0, element: '' })
const lastDoubleClickTimeOn = ref({ time: 0, element: '' })
const lastClickTime = ref(0)
const lastDoubleClickTime = ref(0)
const doubleClickTime = 300;
const tripleClickTime = 300;
let doubleClickTimeout = null;

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
    segments: {} // segmentIndex -> { studied: false, bookmarked: false, markedWords: [] }
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
    
    // Fetch summaries asynchronously
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
    // 1. Load Metadata
    const metaRes = await fetch(`/dictation-app/lessons/${lessonId}/metadata.json`)
    if (!metaRes.ok) throw new Error('Metadata not found')
    currentLessonMetadata.value = await metaRes.json()
    
    // 2. Load audio.json
    const audioRes = await fetch(`/dictation-app/lessons/${lessonId}/audio.json`)
    if (!audioRes.ok) throw new Error('Transcription file not found')
    const audioData = await audioRes.json()
    
    audioSrc.value = `/dictation-app/lessons/${lessonId}/audio.mp3`
    
    // 3. Load Progress
    progressData.value = loadProgress(lessonId)
    currentSegmentId.value = progressData.value.currentSegmentId || 0
    
    // 4. Split segments
    const rawSegments = audioData.segments || []
    const lang = currentLessonMetadata.value?.language || 'en'
    currentLessonSegments.value = filteredSegments(rawSegments, lang)
    
    // 5. Restore segment status
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
      end: getSegmentEnd({ words: currentWords })
    })
  }
  return segments
}

function filteredWords(words = []) {
  return words.filter((w, i, arr) => i === 0 || w.start !== arr[i - 1].start)
}

// --- PLAYER CONTROLS ---
function playFrom(start, stop = -1) {
  if (!audioPlayer.value) return
  audioPlayer.value.currentTime = start
  audioPlayer.value.playbackRate = playSpeed.value
  audioPlayer.value.play().then(() => {
    playing.value = true
    stopTime.value = stop
  }).catch(err => {
    console.error('Audio playback failed:', err)
  })
}

function onTimeUpdate() {
  if (!audioPlayer.value) return
  const curr = audioPlayer.value.currentTime
  currentTime.value = curr
  
  if (stopTime.value > 0 && curr >= stopTime.value) {
    audioPlayer.value.pause()
    stopTime.value = -1
    playing.value = false
  }
}

function onPause() { playing.value = false }
function onPlay() { playing.value = true }
function onEnded() { playing.value = false }

watch(playSpeed, (val) => {
  if (audioPlayer.value) audioPlayer.value.playbackRate = val
})

// --- COMPUTED / CHINESE ---
const isCJK = computed(() => {
  const lang = currentLessonMetadata.value?.language || 'en'
  return ['zh', 'ja', 'ko'].includes(lang)
})

function getMaskedWord(word) {
  return isCJK.value ? '○'.repeat(word.length) : '*'.repeat(word.length)
}

const getCurrentSegment = computed(() => {
  const segment = currentLessonSegments.value?.[currentSegmentId.value]
  if (segment && !segment.studied) {
    segment.studied = true
    saveCurrentProgress()
  }
  return applyChangesToSegment(segment)
})

function applyChangesToSegment(segment) {
  if (!segment) return null
  const lang = currentLessonMetadata.value?.language || 'en'
  if (lang !== 'zh' || !segment.words) return segment
  
  const converter = simplified.value
    ? OpenCC.Converter({ from: 'tw', to: 'cn' })
    : OpenCC.Converter({ from: 'cn', to: 'tw' })
    
  return {
    ...segment,
    words: segment.words.map(word => ({
      ...word,
      word: converter(word.word)
    }))
  }
}

function isHighlighted(word) {
  return currentTime.value >= word.start && currentTime.value <= word.end
}

// --- INTERACTIVE / GESTURES ---
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
    <!-- --- NAVIGATION HEADER --- -->
    <header class="app-header">
      <div class="header-left">
        <button v-if="currentLessonId" class="back-btn" @click="goBackPage">
          <span class="icon">&larr;</span> Back
        </button>
        <span class="app-title" v-else>🎧 Local Dictation</span>
      </div>
      <div class="header-right" v-if="currentLessonId && currentLessonMetadata">
        <span class="lang-tag">{{ currentLessonMetadata.language.toUpperCase() }}</span>
      </div>
    </header>

    <main class="app-main">
      <!-- --- ERROR AREA --- -->
      <div v-if="errorMessage" class="error-banner">
        <span>⚠️ {{ errorMessage }}</span>
      </div>

      <!-- --- SECTION 1: LESSONS LIST --- -->
      <section v-if="!currentLessonId" class="lessons-list-section">
        <h2 class="section-title">My Lessons</h2>
        
        <div v-if="lessons.length === 0" class="empty-state">
          <p>No lessons available yet.</p>
          <p class="instruction-note">Create lessons using: <code>python tools/make_lesson.py &lt;URL&gt; [LANG]</code></p>
        </div>

        <div v-else class="lessons-grid">
          <div 
            v-for="lesson in lessons" 
            :key="lesson.id" 
            class="lesson-card" 
            @click="openLesson(lesson.id)"
          >
            <div class="lesson-meta-top">
              <span class="lesson-lang">{{ lesson.language.toUpperCase() }}</span>
              <span class="lesson-date">{{ lesson.createdAt.split(' ')[0] }}</span>
            </div>
            
            <h3 class="lesson-card-title">{{ lesson.title }}</h3>
            
            <div class="lesson-stats">
              <span>Studied: {{ lesson.studiedCount }} / {{ lesson.segmentCount }}</span>
              <span v-if="lesson.bookmarkedCount > 0" class="bookmarked-count">★ {{ lesson.bookmarkedCount }}</span>
            </div>

            <!-- Segment Progress Bar -->
            <div class="segment-bar">
              <div 
                v-for="(seg, idx) in lesson.segmentsSummary" 
                :key="idx" 
                class="segment-dot"
                :class="{ studied: seg.studied, bookmarked: seg.bookmarked }"
                :title="`Segment ${idx+1}: ${seg.bookmarked ? 'Bookmarked' : (seg.studied ? 'Studied' : 'Not started')}`"
              ></div>
            </div>
          </div>
        </div>
      </section>

      <!-- --- SECTION 2: LESSON DETAIL (DICTATION) --- -->
      <section v-else class="lesson-detail-section">
        <!-- Loader -->
        <div v-if="loadingDetail" class="detail-loader">
          <div class="spinner"></div>
          <p>Loading lesson materials...</p>
        </div>

        <div v-else-if="currentLessonMetadata && currentLessonSegments.length > 0" class="dictation-workspace">
          <!-- Workspace Title -->
          <div class="workspace-meta">
            <h2 class="lesson-title">{{ currentLessonMetadata.title }}</h2>
            <a :href="currentLessonMetadata.source" target="_blank" class="source-link">Source video &rarr;</a>
          </div>

          <!-- Dictation Card -->
          <div class="dictation-card">
            <!-- Settings inside the card -->
            <div class="card-controls">
              <div class="control-group">
                <!-- Play speed selection -->
                <label class="control-label">Speed: </label>
                <select v-model="playSpeed" class="speed-select">
                  <option :value="0.5">0.5x</option>
                  <option :value="0.7">0.7x</option>
                  <option :value="0.8">0.8x</option>
                  <option :value="0.9">0.9x</option>
                  <option :value="1.0">1.0x</option>
                  <option :value="1.2">1.2x</option>
                  <option :value="1.5">1.5x</option>
                </select>
              </div>

              <div class="control-group" v-if="currentLessonMetadata.language === 'zh'">
                <!-- Simplified / Traditional Chinese Switch -->
                <button class="toggle-cc-btn" :class="{ active: simplified }" @click="simplified = !simplified">
                  {{ simplified ? '简体中文' : '繁體中文' }}
                </button>
              </div>

              <!-- Bookmark state button -->
              <button 
                class="bookmark-toggle" 
                :class="{ bookmarked: currentLessonSegments[currentSegmentId]?.bookmarked }"
                @click="toggleBookmark"
              >
                ★ {{ currentLessonSegments[currentSegmentId]?.bookmarked ? 'Bookmarked' : 'Bookmark' }}
              </button>
            </div>

            <!-- Segment Info / Counter -->
            <div class="segment-counter">
              Sentence {{ currentSegmentId + 1 }} / {{ currentLessonSegments.length }}
            </div>

            <!-- Interactive Wave/Touch Overlay for double-clicks, gestures and tap-to-play -->
            <div class="interactive-area-container">
              <div 
                class="touch-overlay"
                @mousedown="handleMouseDown($event, getCurrentSegment)"
                @touchstart="handleTouchStart($event, getCurrentSegment)"
              >
                <div class="overlay-hint">
                  <span>← DblClick Left: Prev</span>
                  <span>Tap: Play/Pause</span>
                  <span>DblClick Right: Next &rarr;</span>
                </div>
              </div>

              <!-- Word Chips Container -->
              <div class="word-chips-container">
                <div class="chips-flex">
                  <span
                    v-for="(word, key) in filteredWords(getCurrentSegment?.words)"
                    :key="key"
                    class="word-chip"
                    :class="{ 'highlighted': isHighlighted(word), 'marked': word.marked }"
                    @mousedown="handleMouseDownOnWord($event, word)"
                    @touchstart="handleMouseDownOnWord($event, word)"
                  >
                    <span v-if="masked" class="masked-text">{{ getMaskedWord(word.word) }}</span>
                    <span v-else class="revealed-text">{{ word.word }}</span>
                  </span>
                </div>
              </div>
            </div>

            <!-- Show/Hide Hold Button -->
            <div class="show-hide-control">
              <button
                class="hold-to-show-btn"
                :class="{ active: !masked || keepShowing }"
                @mousedown="toggleGlobalHide(true)"
                @mouseup="keepShowing ? null : toggleGlobalHide(false)"
                @mouseleave="keepShowing ? null : (masked = true)"
                @touchstart="toggleGlobalHide(true)"
                @touchend="keepShowing ? null : toggleGlobalHide(false)"
              >
                {{ keepShowing ? 'Showing Locked' : (masked ? 'Hold to Show' : 'Release to Hide') }}
              </button>
              <span class="btn-hint">Tip: Double tap to lock showing.</span>
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
  </div>
</template>

<style scoped>
/* Base container styling matching local system variables */
.app-container {
  max-width: 960px;
  margin: 0 auto;
  padding: 1rem;
  font-family: var(--sans);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-column: column;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2rem;
}

.app-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-h);
}

.back-btn {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-h);
  padding: 0.5rem 1rem;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.back-btn:hover {
  background: var(--border);
}

.lang-tag {
  background: var(--accent-bg);
  border: 1px solid var(--accent-border);
  color: var(--accent);
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 600;
}

.app-main {
  flex-grow: 1;
}

.error-banner {
  background: #fdf2f2;
  border: 1px solid #f8b4b4;
  color: #9b1c1c;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
  font-size: 0.9rem;
}

/* LESSONS LIST STYLE */
.section-title {
  font-size: 1.5rem;
  margin-bottom: 1.5rem;
  color: var(--text-h);
}

.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  background: var(--code-bg);
  border-radius: 12px;
  border: 1px dashed var(--border);
}

.instruction-note {
  margin-top: 1rem;
  font-size: 0.9rem;
  color: var(--text);
}

.instruction-note code {
  background: var(--bg);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  border: 1px solid var(--border);
}

.lessons-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
}

.lesson-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.5rem;
  cursor: pointer;
  box-shadow: var(--shadow);
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.lesson-card:hover {
  transform: translateY(-4px);
  border-color: var(--accent);
}

.lesson-meta-top {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  color: var(--text);
  margin-bottom: 0.75rem;
}

.lesson-lang {
  font-weight: 600;
  color: var(--accent);
}

.lesson-card-title {
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--text-h);
  margin: 0 0 1rem;
  line-height: 1.3;
}

.lesson-stats {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  margin-bottom: 1rem;
  color: var(--text);
}

.bookmarked-count {
  color: #d97706;
  font-weight: 600;
}

/* SEGMENT PROGRESS BAR */
.segment-bar {
  display: flex;
  gap: 3px;
  height: 6px;
  width: 100%;
  background: var(--code-bg);
  border-radius: 3px;
  overflow: hidden;
}

.segment-dot {
  flex-grow: 1;
  background: #e5e7eb;
}

.segment-dot.studied {
  background: #10b981; /* Green */
}

.segment-dot.bookmarked {
  background: #f59e0b; /* Yellow/Orange */
}

/* LESSON DETAIL / DICTATION */
.dictation-workspace {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.workspace-meta {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.lesson-title {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-h);
  margin: 0;
  max-width: 75%;
}

.source-link {
  font-size: 0.9rem;
  color: var(--accent);
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}

.dictation-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  position: relative;
}

.card-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 1rem;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.control-label {
  font-size: 0.85rem;
  font-weight: 500;
}

.speed-select {
  padding: 0.3rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-h);
  font-size: 0.85rem;
  cursor: pointer;
}

.toggle-cc-btn {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-h);
  padding: 0.3rem 0.6rem;
  font-size: 0.85rem;
  cursor: pointer;
}

.toggle-cc-btn.active {
  background: var(--accent-bg);
  border-color: var(--accent-border);
  color: var(--accent);
}

.bookmark-toggle {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: #b45309;
  padding: 0.3rem 0.8rem;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
}

.bookmark-toggle.bookmarked {
  background: #fef3c7;
  border-color: #fcd34d;
  color: #b45309;
}

.segment-counter {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  text-align: center;
}

/* INTERACTIVE DICTATION CONTAINER */
.interactive-area-container {
  position: relative;
  border-radius: 12px;
  background: var(--code-bg);
  padding: 2.5rem 1.5rem;
  overflow: hidden;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.touch-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 0.5rem;
}

.overlay-hint {
  display: flex;
  justify-content: space-between;
  width: 100%;
  font-size: 0.72rem;
  color: var(--text);
  opacity: 0.3;
  pointer-events: none;
}

.word-chips-container {
  position: relative;
  z-index: 2; /* Sits above touch overlay to receive click events on words */
  width: 100%;
  text-align: center;
}

.chips-flex {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
}

.word-chip {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 0.4rem 0.8rem;
  border-radius: 8px;
  font-size: 1.1rem;
  font-weight: 500;
  color: var(--text-h);
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.word-chip:hover {
  border-color: var(--accent);
  background: var(--accent-bg);
}

.word-chip.highlighted {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.word-chip.highlighted .masked-text {
  color: rgba(255, 255, 255, 0.7);
}

.word-chip.marked {
  background: #d1fae5;
  border-color: #34d399;
  color: #065f46;
}

.masked-text {
  letter-spacing: 0.1rem;
  color: #a1a1aa;
}

/* HOLD TO SHOW CONTROL */
.show-hide-control {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.hold-to-show-btn {
  width: 100%;
  max-width: 280px;
  padding: 1rem 1.5rem;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-h);
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow);
  transition: all 0.15s ease;
}

.hold-to-show-btn:hover {
  background: var(--code-bg);
}

.hold-to-show-btn.active {
  background: var(--accent-bg);
  border-color: var(--accent-border);
  color: var(--accent);
  transform: scale(0.98);
}

.btn-hint {
  font-size: 0.75rem;
  color: var(--text);
  opacity: 0.7;
}

/* GENERAL LOADER */
.detail-loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 1rem;
  gap: 1rem;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>