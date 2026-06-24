<template>
  <v-container class="pa-6">

    <h2 class="mb-4">Lessons</h2>

    <v-btn class="mb-4" @click="loadLessons">
      Reload
    </v-btn>

    <v-card
      v-for="lesson in lessons"
      :key="lesson.id"
      class="mb-3 pa-3"
      @click="openLesson(lesson)"
      style="cursor:pointer;"
    >
      <div><strong>{{ lesson.title }}</strong></div>
      <div class="text-caption">{{ lesson.id }}</div>
    </v-card>

  </v-container>
</template>

<script setup>
import { ref } from 'vue'

const lessons = ref([])

function loadLessons() {
  // 仮データ（まずは動作確認用）
  lessons.value = [
    {
      id: '20260625_065744',
      title: 'Sample Lesson 1'
    }
  ]
}

function openLesson(lesson) {
  console.log('open:', lesson)
}
</script>