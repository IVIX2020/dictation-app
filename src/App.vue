<template>
  <v-container class="pa-6 text-center">

    <h2 class="mb-6">Dictation App</h2>

    <!-- file input -->
    <v-file-input
      v-model="file"
      label="Import lesson.zip"
      accept=".zip"
      prepend-icon="mdi-folder-zip"
    />

    <!-- import button -->
    <v-btn
      class="mt-4"
      color="primary"
      :disabled="!file"
      @click="handleImport"
    >
      Import Lesson
    </v-btn>

    <!-- status -->
    <div class="mt-6">
      <v-alert v-if="status" type="info">
        {{ status }}
      </v-alert>
    </div>

  </v-container>
</template>

<script setup>
import { ref } from 'vue'
import JSZip from 'jszip'

const file = ref(null)
const status = ref('')

async function handleImport() {
  try {
    status.value = 'Reading zip...'

    const zip = await JSZip.loadAsync(file.value)

    const metadata = JSON.parse(
      await zip.file('metadata.json').async('string')
    )

    const transcript = JSON.parse(
      await zip.file('transcript.json').async('string')
    )

    const audioBlob = await zip.file('audio.mp3').async('blob')

    // 仮保存（まずはメモリだけ）
    const lesson = {
      id: metadata.id,
      title: metadata.title,
      transcript,
      audioBlob,
    }

    console.log('Imported lesson:', lesson)

    status.value = `Imported: ${lesson.title}`

  } catch (e) {
    console.error(e)
    status.value = 'Import failed'
  }
}
</script>