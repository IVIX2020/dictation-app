<template>
  <v-container fluid class="pa-0 d-flex flex-column align-center justify-center fill-height">
    <!-- Error display -->
    <v-col v-if="errorMessage" class="text-center">
      <v-alert type="error" class="ma-4">{{ errorMessage }}</v-alert>
    </v-col>

    <!-- Back button -->
    <v-btn
      @click="goBackPage"
      variant="text"
      class="text-caption"
      style="position: absolute; top: 12px; left: 12px; z-index: 10;"
      aria-label="Go back"
    >
      <v-icon start size="16">mdi-arrow-left</v-icon> back
    </v-btn>

    <!-- Loading spinner -->
    <v-col
      v-if="!localDoc"
      class="fill-height d-flex align-center justify-center"
    >
      <v-progress-circular indeterminate size="32" width="3" />
    </v-col>

    <!-- Main content -->
    <v-col
      v-else
      cols="12"
      md="8"
      class="d-flex flex-column align-center justify-center fill-height"
    >
      <v-card
        elevation="2"
        class="pa-4 d-flex flex-column align-center justify-start"
        style="width: 100%; max-width: 600px; position: relative;"
      >
        <!-- Settings menu -->
        <v-menu location="bottom" :close-on-content-click="false">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              size="small"
              variant="text"
              icon
              class="position-absolute"
              style="top: 12px; left: 12px; z-index: 10;"
              aria-label="Settings"
            >
              <v-icon size="18">mdi-cog</v-icon>
            </v-btn>
          </template>
          <v-list>
            <v-list-item v-if="localDoc.language === 'zh'">
              <v-switch
                v-model="simplified"
                color="primary"
                label="Simplified Chinese"
                hide-details
                aria-label="Toggle Simplified Chinese"
              />
            </v-list-item>
            <v-list-item>
              <v-btn
                size="small"
                variant="text"
                @click="playSpeed = Math.max(0.1, playSpeed - 0.1)"
                aria-label="Decrease playback speed"
              >-</v-btn>
              <span class="mx-2 text-caption">{{ formattedSpeed }}x</span>
              <v-btn
                size="small"
                variant="text"
                @click="playSpeed = Math.min(2.0, playSpeed + 0.1)"
                aria-label="Increase playback speed"
              >+</v-btn>
            </v-list-item>
          </v-list>
        </v-menu>

        <!-- Bookmark button -->
        <v-btn
          @click="toggleBookmark"
          variant="text"
          size="small"
          class="position-absolute text-caption"
          style="top: 12px; right: 12px; z-index: 10;"
          :class="{ 'bookmarked': localDoc.segments[currentSegmentId].bookmarked }"
          :aria-label="localDoc.segments[currentSegmentId].bookmarked ? 'Remove bookmark' : 'Add bookmark'"
        >
          {{ localDoc.segments[currentSegmentId].bookmarked ? 'Bookmarked' : 'Bookmark' }}
        </v-btn>

        <!-- Segment navigation -->
        <div class="text-caption mt-2 mb-4">
          {{ currentSegmentId + 1 }} / {{ filteredSegments(localDoc.segments).length }}
        </div>

        <!-- Segment content -->
        <div
          class="background-overlay"
          @mousedown="handleMouseDown($event, getCurrentSegment)"
          @touchstart="handleTouchStart($event, getCurrentSegment)"
          @touchend="handleTouchEnd"
          v-touch="{ left: getNextSegment, right: getPreviousSegment }"
          aria-hidden="true"
        ></div>

        <!-- Word chips -->
        <v-card-text class="text-center pa-0" style="z-index: 2;">
          <v-chip
            v-for="(word, key) in filteredWords(getCurrentSegment.words)"
            :key="key"
            class="ma-1"
            variant="tonal"
            :class="{ 'highlighted-chip': isHighlighted(word), 'marked-chip': word.marked }"
            @mousedown.stop="handleMouseDownOnWord($event, word)"
            @touchstart.stop="handleMouseDownOnWord($event, word)"
            :aria-label="`Word: ${word.word}${word.marked ? ', marked' : ''}`"
          >
            <span v-if="masked" class="text-disabled">{{ getMaskedWord(word.word) }}</span>
            <span v-else>{{ word.word }}</span>
          </v-chip>
        </v-card-text>

        <!-- Show/Hide button -->
        <v-btn
          class="mt-6 text-caption"
          @mousedown="toggleGlobalHide(true)"
          @mouseup="keepShowing ? null : toggleGlobalHide(false)"
          @mouseleave="keepShowing ? null : (masked = true)"
          @touchstart="toggleGlobalHide(true)"
          @touchend="keepShowing ? null : toggleGlobalHide(false)"
          variant="tonal"
          :aria-label="keepShowing ? 'Quit showing' : (masked ? 'Show words' : 'Hide words')"
        >
          {{ keepShowing ? 'Quit Showing' : (masked ? 'Show' : 'Hide') }}
        </v-btn>
      </v-card>
    </v-col>
  </v-container>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { doc, getDoc, serverTimestamp, updateDoc } from 'firebase/firestore';
import { db } from '@/firebase/config';
import { Howl } from 'howler';
import * as OpenCC from 'opencc-js';

// State
const route = useRoute();
const id = route.params.id;
const localDoc = ref(null);
const errorMessage = ref('');
const simplified = ref(false);
const playing = ref(false);
const currentTime = ref(0);
const currentSegmentId = ref(0);
const stopTime = ref(-1);
const playSpeed = ref(1.0);
const keepShowing = ref(false);
const masked = ref(true);
const lastClickTimeOn = ref({ time: 0, element: '' });
const lastDoubleClickTimeOn = ref({ time: 0, element: '' });
const lastClickTime = ref(0);
const lastDoubleClickTime = ref(0);
const doubleClickTime = 300;
const tripleClickTime = 300;
let doubleClickTimeout = null;
let howl = null;

// Constants
const errorSegmentThreshold = 5.0;
const gapThreshold = 0.1;

// Computed properties
const getCurrentSegment = computed(() => {
  const segment = localDoc.value?.segments?.[currentSegmentId.value];
  if (segment && !segment.studied) updateSegmentAsStudied();
  return applyChangesToSegment(segment);
});

const formattedSpeed = computed(() => playSpeed.value.toFixed(1));

// Watchers
watch(currentTime, (val) => {
  if (stopTime.value > 0 && val > stopTime.value) {
    howl?.pause();
    playing.value = false;
  }
});

watch(playSpeed, (val) => {
  howl?.rate(val);
});

// Fetch document from Firestore
async function fetchDocumentById(id) {
  try {
    if (!id) throw new Error('Invalid document ID');
    const docRef = doc(db, 'results', id);
    const docSnap = await getDoc(docRef);
    if (!docSnap.exists()) throw new Error('Document not found');
    const data = docSnap.data();
    if (!data.audioUrl || !data.segments?.length) throw new Error('Invalid document data');
    const filtered = filteredSegments(data.segments);
    localDoc.value = {
      id: docSnap.id,
      ...data,
      segments: filtered.length === data.segments.length ? data.segments : filtered,
    };
    currentSegmentId.value = data.currentSegmentId || 0;
    load(data.audioUrl);
  } catch (error) {
    console.error('Error fetching document:', error);
    errorMessage.value = error.message;
  }
}

// Update Firestore document
async function updateDocument() {
  try {
    if (!localDoc.value?.id) return;
    const refDoc = doc(db, 'results', localDoc.value.id);
    await updateDoc(refDoc, {
      currentSegmentId: currentSegmentId.value,
      segments: localDoc.value.segments,
      updatedAt: serverTimestamp(),
    });
  } catch (error) {
    console.error('Error updating document:', error);
    errorMessage.value = 'Failed to update document';
  }
}

// Mark segment as studied
async function updateSegmentAsStudied() {
  if (!localDoc.value?.segments?.[currentSegmentId.value]) return;
  localDoc.value.segments[currentSegmentId.value].studied = true;
  await updateDocument();
}

// Toggle bookmark
async function toggleBookmark() {
  if (!localDoc.value?.segments?.[currentSegmentId.value]) return;
  const seg = localDoc.value.segments[currentSegmentId.value];
  seg.bookmarked = !seg.bookmarked;
  await updateDocument();
}

// Load audio
function load(url) {
  howl?.unload();
  howl = new Howl({
    src: [url],
    html5: true,
    onplay: () => {
      playing.value = true;
      updateTime();
    },
    onend: () => {
      playing.value = false;
    },
    onloaderror: (_, err) => {
      console.error('Load error:', err);
      errorMessage.value = 'Failed to load audio';
    },
    onplayerror: (_, err) => {
      console.error('Play error:', err);
      errorMessage.value = 'Failed to play audio';
    },
  });
}

// Update current time during playback
function updateTime() {
  if (howl && playing.value) {
    currentTime.value = howl.seek();
    requestAnimationFrame(updateTime);
  }
}

// Play audio from start to optional stop time
function playFrom(start, stop = -1) {
  if (!howl) return;
  howl.seek(start);
  howl.play();
  stopTime.value = stop;
}

// Mask words for display
function getMaskedWord(word) {
  const isCJK = ['zh', 'ko', 'ja'].includes(localDoc.value?.language);
  return isCJK ? '○'.repeat(word.length) : '*'.repeat(word.length);
}

// Apply Chinese conversion to segment
function applyChangesToSegment(segment) {
  if (!segment) return null;
  return {
    ...segment,
    words: segment.words.map(word => ({
      ...word,
      word: simplified.value && localDoc.value.language === 'zh'
        ? OpenCC.Converter({ from: 'tw', to: 'cn' })(word.word)
        : OpenCC.Converter({ from: 'cn', to: 'tw' })(word.word),
    })),
  };
}

// Segment timing helpers
function getSegmentStart(seg) { return seg?.words[0]?.start ?? seg?.start ?? 0; }
function getSegmentEnd(seg) { return seg?.words.at(-1)?.end ?? seg?.end ?? 0; }
function getSegmentDuration(seg) { return getSegmentEnd(seg) - getSegmentStart(seg); }

// Filter and split segments
function filteredSegments(segments) {
  return segments.flatMap(s => splitSegmentByGapRecursive(s, gapThreshold, errorSegmentThreshold));
}

function splitSegmentByGapRecursive(segment, gapThreshold, maxLength) {
  let segments = splitSegment(segment, gapThreshold);
  while (segments.some(s => getSegmentDuration(s) > maxLength)) {
    const temp = segments.flatMap(s =>
      getSegmentDuration(s) > maxLength ? splitSegment(s, gapThreshold) : s
    );
    if (temp.length === segments.length) break;
    segments = temp;
  }
  return segments;
}

function splitSegment(segment, gapThreshold) {
  const segments = [];
  const words = segment.words || [];
  let currentWords = [];
  let currentStart = getSegmentStart(segment);

  for (let i = 0; i < words.length; i++) {
    const word = words[i];
    currentWords.push(word);
    const nextStart = words[i + 1]?.start ?? word.end;
    if (nextStart - word.end >= gapThreshold) {
      segments.push({ words: currentWords, start: currentStart, end: word.end, ...segment });
      currentWords = [];
      currentStart = nextStart;
    }
  }
  if (currentWords.length) {
    segments.push({ words: currentWords, start: currentStart, end: getSegmentEnd({ words: currentWords }), ...segment });
  }
  return segments;
}

// Filter duplicate words
function filteredWords(words = []) {
  return words.filter((w, i, arr) => i === 0 || w.start !== arr[i - 1].start);
}

// Highlight current word
function isHighlighted(word) {
  return currentTime.value >= word.start && currentTime.value <= word.end;
}

// Toggle show/hide
function toggleGlobalHide(isVisible) {
  const now = Date.now();
  const last = lastClickTimeOn.value;
  keepShowing.value = false;
  if (now - last.time < doubleClickTime && last.element === 'hide' && isVisible) {
    keepShowing.value = true;
    masked.value = false;
  } else {
    masked.value = !isVisible;
    lastClickTimeOn.value = { time: now, element: 'hide' };
  }
}

// Handle word clicks
function handleMouseDownOnWord(event, word) {
  event.preventDefault();
  const currentTime = Date.now();
  if (currentTime - lastDoubleClickTimeOn.value.time < doubleClickTime && lastDoubleClickTimeOn.value.element === 'word') {
    word.marked = !word.marked;
    if (word.marked) localDoc.value.segments[currentSegmentId.value].bookmarked = true;
    updateDocument();
  } else if (currentTime - lastClickTimeOn.value.time < doubleClickTime && lastClickTimeOn.value.element === 'word') {
    lastDoubleClickTimeOn.value = { time: currentTime, element: 'word' };
  } else {
    playFrom(word.start, filteredWords(getCurrentSegment.value?.words || []).at(-1)?.end || 0);
    lastClickTimeOn.value = { time: currentTime, element: 'word' };
  }
}

// Navigation
function goBackPage() {
  window.history.back();
}

function getPreviousSegment() {
  if (currentSegmentId.value > 0) currentSegmentId.value--;
  updateDocument();
}

function getNextSegment() {
  if (currentSegmentId.value < filteredSegments(localDoc.value?.segments || []).length - 1) {
    currentSegmentId.value++;
  }
  updateDocument();
}

function getPreviousBookmarkedSegment() {
  for (let i = currentSegmentId.value - 1; i >= 0; i--) {
    if (localDoc.value.segments[i].bookmarked) {
      currentSegmentId.value = i;
      updateDocument();
      break;
    }
  }
}

function getNextBookmarkedSegment() {
  for (let i = currentSegmentId.value + 1; i < filteredSegments(localDoc.value?.segments || []).length; i++) {
    if (localDoc.value.segments[i].bookmarked) {
      currentSegmentId.value = i;
      updateDocument();
      break;
    }
  }
}

// Handle mouse/touch events
function handleMouseDown(event, segment) {
  const cardWidth = event.currentTarget.offsetWidth;
  const clickX = event.offsetX;
  const isLeft = clickX < cardWidth / 2;
  const currentTime = Date.now();

  if (currentTime - lastDoubleClickTime.value < tripleClickTime) {
    clearTimeout(doubleClickTimeout);
    handleTripleClick(isLeft);
  } else if (currentTime - lastClickTime.value < doubleClickTime) {
    lastDoubleClickTime.value = currentTime;
    doubleClickTimeout = setTimeout(() => {
      handleDoubleClick(isLeft);
    }, tripleClickTime);
  } else {
    handleTap(segment);
  }

  lastClickTime.value = currentTime;
}

function handleTouchStart(event, segment) {
  event.preventDefault();
  handleMouseDown(event, segment);
}

function handleTouchEnd(event) {
  event.preventDefault();
}

function handleTap(segment) {
  if (!segment) return;
  if (playing.value) {
    howl?.pause();
    stopTime.value = howl?.seek() || 0;
    playing.value = false;
  } else {
    playFrom(getSegmentStart(segment), getSegmentEnd(segment));
  }
}

function handleDoubleClick(isLeft) {
  isLeft ? getPreviousSegment() : getNextSegment();
}

function handleTripleClick(isLeft) {
  isLeft ? getPreviousBookmarkedSegment() : getNextBookmarkedSegment();
}

// Lifecycle hooks
onMounted(() => {
  if (id) {
    fetchDocumentById(id);
  } else {
    errorMessage.value = 'Invalid document ID';
  }
});

onBeforeUnmount(async () => {
  await updateDocument();
  howl?.unload();
});
</script>

<style scoped>
.fill-height {
  height: 100vh;
}
.background-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0);
  z-index: 1;
}
.text-caption {
  z-index: 2;
}
.highlighted-chip {
  background-color: #757575 !important; /* Gray for dark/light themes */
}
.marked-chip {
  background-color: #d4edda !important; /* Light green */
}
.bookmarked {
  background-color: #d4edda !important;
}
.text-disabled {
  color: #bdbdbd;
}
</style>