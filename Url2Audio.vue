<template>
  <v-container>
    <v-row justify="center">
      <v-col cols="12" md="8">
        <!-- YouTube URL form -->
        <v-form @submit.prevent="submitForm" class="mb-4">
          <v-tabs v-model="selectedTab" background-color="deep-purple accent-4" dark>
            <v-tab>Upload MP3 File</v-tab>
            <v-tab>Enter YouTube URL</v-tab>
          </v-tabs>
          <v-tabs-items v-model="selectedTab">
            <!-- Upload MP3 File Tab -->
            <v-tab-item v-if="selectedTab === 0">
              <v-file-input
                v-model="selectedFile"
                label="Upload an MP3 file"
                accept="audio/mp3"
                prepend-icon="mdi-file-music-outline"
                required
              ></v-file-input>
              <v-text-field
                v-model="enteredTitle"
                label="Enter Title"
                prepend-icon="mdi-text"
                required
              ></v-text-field>
            </v-tab-item>

            <!-- Enter YouTube URL Tab -->
            <v-tab-item v-if="selectedTab === 1">
              <v-text-field
                variant="underlined"
                v-model="enteredUrl"
                label="Enter the URL of YouTube or Netflix"
                :prepend-icon="getPrependIcon(detectedProvider)"
                required
              ></v-text-field>
              <v-alert v-if="enteredUrl && detectedProvider != 'youtube'">This video service is not supported.</v-alert>
            </v-tab-item>
          </v-tabs-items>

          <v-select
            variant="underlined"
            v-model="selectedLanguage"
            :items="languages"
            label="Transcribed in"
            prepend-icon="mdi-translate"
            required
          ></v-select>
          <v-btn type="submit" color="black" style="margin-bottom:10px" :disabled=" !selectedLanguage || (!enteredUrl && !selectedFile) ">-> Convert to Audio with {{ selectedLanguage }}</v-btn>
          <v-alert v-if="errorMessage">{{errorMessage}}</v-alert>
        </v-form>

        <!-- Divider for separating the form from the list -->
        <v-divider class="my-4"></v-divider>
      </v-col>

      <!-- List of uploaded audio files -->
      <v-col cols="12" md="8" v-for="doc in transcriptedDocs" :key="doc.id">
        <v-card
          :variant="isDocUpdated(doc) ? 'outlined' : 'outlined'"
          @click="navigateToDetail(doc)"
          style="cursor: pointer; position: relative;"
          :class="{'highlightedDoc' : isDocUpdated(doc)}"
        >
          <v-row>
            <v-col cols="12">
              <div class="segment-container">
                <div
                  v-for="(segment, id) in doc.segments"
                  :key="id"
                  :style="getSegmentStyle(segment)"
                  class="segment-box"
                >
                </div>
              </div>
              <v-card-text class="mb-2 text-wrap">
                <strong>{{ doc.title }}</strong>
              </v-card-text>
              <v-card-text justify="end" align="end">
                <span> studied {{ studiedSegmentCount(doc) }} and </span>
                <span> bookmarked {{ bookmarkedSegmentCount(doc) }} in {{ doc.segments.length }}</span>
                <br>{{formatDate(doc.updatedAt)}}
              </v-card-text>
              
            </v-col>
          </v-row>
        </v-card>
        <div justify="end" align="end" style="cursor:pointer; margin-right:5px;"><span @click.stop="deleteDoc(doc)" style="color:darkgray;">delete</span></div>
      </v-col>

      <v-col cols="12" md="8" v-for="doc in untranscriptedDocs" :key="doc.id">
        <v-card
          variant="outlined"
          :loading="doc.status=='Transcribing ...' || doc.status== 'Downloading Audio File'"
          :disabled="doc.status=='Transcribing ...' || doc.status == 'Downloading Audio File'"
        >
          <v-row no-gutters>
            <v-col cols="12">
              <v-card-text class="text-subtitle-1 mb-2 text-wrap">
                <span><strong>{{ doc.title ? doc.title : "now processing" }}</strong></span><br>
                {{ doc.status }} / {{ doc.language ? doc.language :"unknown language"}} / {{ doc.ownedBy }} / {{ doc.duration }}
              </v-card-text>
              <v-card-text justify="end" align="end" v-if="doc.status=='Transcribing ...' || doc.status == 'Downloading Audio File'">
                {{ formatDate(doc.createdAt) }}
              </v-card-text>
              
              <!-- 複数の音声ファイルがある場合の表示 -->
              <div v-if="doc.audioUrls && doc.audioUrls.length > 1">
                <v-card-text v-for="(audioUrl, index) in doc.audioUrls" :key="index" @click="uploadAudio(doc)" style="cursor: pointer;">
                  -> start to transcribe {{ index + 1 }} / {{ doc.audioUrls.length }}
                </v-card-text>
              </div>
              
              <!-- 音声ファイルが1つだけ、または存在しない場合の表示 -->
              <div v-else>
                <v-card-text color="primary" @click="uploadAudio(doc)" style="cursor: pointer;">
                  -> Start to transcribe
                </v-card-text>
              </div>

            </v-col>
          </v-row>
        </v-card>
        <span @click.stop="deleteDoc(doc)" style="color:darkgray; cursor:pointer">cancel</span>
      </v-col>

    </v-row>
  </v-container>
</template>



<script>
import axios from 'axios';
import router from '@/router';
import { collection, query, where, orderBy, onSnapshot, doc, deleteDoc } from 'firebase/firestore';
import { db } from '@/firebase/config';

export default {
  props: {
    userName: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      selectedTab: 0,
      enteredTitle: '',
      globalHide: true,
      selectedLanguage: localStorage.getItem('selectedLanguage') || 'zh',
      languages: [
        { title: 'English', value: 'en' },
        { title: 'Chinese', props: { subtitle: 'transcribed in Traditional Chinese by default but you can change it anytime' }, value: 'zh' },
        { title: 'other languages', props: { subtitle: 'automatically detected (with some risk of error)' }, value: 'other languages' },
      ],
      enteredUrl: '',
      enteredLoginId: localStorage.getItem('enteredLoginId') || '',
      enteredPassword: localStorage.getItem('enteredPassword') || '',
      downloadLink: '',
      errorMessage: '',
      transcription: [],
      selectedFile: null,
      currentSeek: 0,
      audioUrl: null,
      documentId: '',
      clickStartTime: null,
      delayThreshold: 1000,
      timeoutId: null,
      isMouseInside: false,
      firestoreResults: [],
      inputName: '',
    };
  },
  computed: {
    updatedTranscription() {
      return this.transcription.map(segment => ({
        ...segment,
        currentplayed: this.currentSeek >= segment.start && this.currentSeek <= segment.end,
      }));
    },
    currentPlayedSegments() {
      return this.updatedTranscription.filter(segment => segment.currentplayed);
    },
    filteredSegment() {
      return this.updatedTranscription.find(segment => segment.currentplayed);
    },
    untranscriptedDocs() {
      return this.firestoreResults.filter(doc => !doc.segments);
    },
    transcriptedDocs() {
      return this.firestoreResults.filter(doc => doc.segments);
    },
    detectedProvider() {
      try {
        const host = new URL(this.enteredUrl).hostname.toLowerCase();
        if (host.includes('youtube.com') || host.includes('youtu.be')) return 'youtube';
        if (host.includes('netflix')) return 'netflix';
        return null;
      } catch {
        return null;
      }
    },
  },
  watch: {
    selectedLanguage(val) {
      localStorage.setItem('selectedLanguage', val);
    },
    userName: 'fetchFirestoreData',
    selectedFile(val) {
      this.enteredTitle = val?.name || '';
    },
  },
  methods: {
    async submitForm() {
      this.errorMessage = '';
      if (!this.userName) {
        this.$emit('request-login');
        await new Promise(resolve => {
          const interval = setInterval(() => {
            if (this.userName) clearInterval(interval), resolve();
          }, 100);
        });
      }
      const requestData = new FormData();
      if (this.selectedTab === 0 && this.selectedFile) {
        requestData.append('file', this.selectedFile);
        requestData.append('title', this.enteredTitle);
        requestData.append('language', this.selectedLanguage === 'other languages' ? '' : this.selectedLanguage);
        requestData.append('ownedBy', this.userName);
        requestData.append('detectedProvider', this.detectedProvider);
      } else if (this.selectedTab === 1 && this.enteredUrl) {
        localStorage.setItem('enteredLoginId', this.enteredLoginId);
        localStorage.setItem('enteredPassword', this.enteredPassword);
        requestData.append('youtubeUrl', this.enteredUrl);
        requestData.append('language', this.selectedLanguage === 'other languages' ? '' : this.selectedLanguage);
        requestData.append('ownedBy', this.userName);
        requestData.append('detectedProvider', this.detectedProvider);
        this.enteredUrl = '';
      }
      try {
        const res = await axios.post('https://asia-northeast1-mysaktools.cloudfunctions.net/url2audio', requestData, { responseType: 'blob' });
        const blob = new Blob([res.data], { type: 'audio/mp3' });
        this.audioUrl = URL.createObjectURL(blob);
        this.documentId = this.audioUrl.split('/').pop().replace('.mp3', '');
        this.fetchFirestoreData();
        this.selectedFile = null;
      } catch (e) {
        console.error(e);
        this.errorMessage = 'Failed to fetch or upload the file.';
      }
    },
    async uploadAudio(doc) {
      const documentId = doc.audioUrl?.split('/').pop().replace('.mp3', '');
      const payload = { audioUrl: doc.audioUrl, language: doc.language, document_id: documentId };
      try {
        const res = await fetch('https://asia-northeast1-mysaktools.cloudfunctions.net/audio2text', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('Upload failed');
        console.log(await res.json());
      } catch (e) {
        console.error(e);
        this.errorMessage = 'audioUrlのアップロードに失敗しました。';
      }
    },
    fetchFirestoreData() {
      const q = query(collection(db, 'results'), orderBy('updatedAt', 'desc'), where('ownedBy', '==', this.userName));
      this.unsubscribe = onSnapshot(q, (snap) => {
        this.firestoreResults = snap.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      }, err => {
        console.error(err);
        this.errorMessage = 'Failed to fetch Firestore data.';
      });
    },
    async deleteDocEntry(docItem) {
      if (!confirm(`Delete ${docItem.title || 'this document'}?`)) return;
      try {
        await deleteDoc(doc(db, 'results', docItem.id));
        this.firestoreResults = this.firestoreResults.filter(d => d.id !== docItem.id);
      } catch (e) {
        console.error(e);
        alert('Failed to delete document.');
      }
    },
    getPrependIcon(provider) {
      return provider === 'netflix' ? 'mdi-netflix' : provider === 'youtube' ? 'mdi-youtube' : 'mdi-link-edit';
    },
    isDocUpdated(doc) {
      return doc?.createdAt?.toDate().getTime() !== doc?.updatedAt?.toDate().getTime();
    },
    getSegmentStyle(segment) {
      const color = segment.studied || segment.bookmarked ? 'gray' : 'lightgray';
      return { backgroundColor: color, height: '3px', margin: '0px', flexGrow: 1 };
    },
    studiedSegmentCount(doc) {
      return Array.isArray(doc?.segments) ? doc.segments.filter(s => s.studied).length : 0;
    },
    bookmarkedSegmentCount(doc) {
      return Array.isArray(doc?.segments) ? doc.segments.filter(s => s.bookmarked).length : 0;
    },
    navigateToDetail(doc) {
      if (!doc?.id) return;
      router.push(`/AudioDetail/${doc.id}`);
    },
    playAudio(startTime) {
      this.$refs.audioPlayer?.playFrom(startTime);
    },
    handleMouseDown() {
      if (this.isMouseInside) {
        this.clickStartTime = Date.now();
        this.timeoutId = setTimeout(() => console.log('1 second passed'), this.delayThreshold);
      }
    },
    handleMouseUp() {
      this.cleanup();
    },
    handleMouseLeave() {
      this.cleanup();
      this.isMouseInside = false;
    },
    handleMouseEnter() {
      this.isMouseInside = true;
    },
    cleanup() {
      clearTimeout(this.timeoutId);
      this.timeoutId = null;
      this.clickStartTime = null;
    },
    updateHide(status) {
      this.globalHide = status;
    },
    formatDate(ts) {
      return ts ? new Intl.DateTimeFormat('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(ts.toDate()) : '';
    }
  },
  mounted() {
    window.dispatchEvent(new Event('resize'));
    this.fetchFirestoreData();
  },
  beforeUnmount() {
    this.unsubscribe?.();
  }
};
</script>


<style>
.highlightedDoc{
  background:lightgray;
  border: white;
}
.text-truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.text-wrap {
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.segment-container {
  display: flex;
  justify-content: space-between; /* セグメント間のスペースを均等にする */
  align-items: center;
  width: 100%; /* コンテナ全体の幅を指定 */
}

.segment-box {
  max-width: calc(100% / var(--segment-count) - 10px); /* 各セグメントの最大幅を設定 */
}
</style>
