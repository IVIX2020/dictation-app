<script setup>
import { ref, onMounted } from 'vue'

const lessons = ref([])

async function loadLessons() {
  const res = await fetch('/lessons/lessons.json')
  lessons.value = await res.json()
}

function openLesson(lesson) {
  window.location.href = `/lesson.html?id=${lesson.id}`
}

onMounted(() => {
  loadLessons()
})
</script>

<template>
  <v-container class="pa-6">

    <h2 class="mb-4">Lessons</h2>

    <v-card
      v-for="lesson in lessons"
      :key="lesson.id"
      class="mb-3 pa-3"
      @click="openLesson(lesson)"
      style="cursor:pointer;"
    >
      <div><strong>{{ lesson.title }}</strong></div>
      <div class="text-caption">{{ lesson.createdAt }}</div>
    </v-card>

  </v-container>
</template>