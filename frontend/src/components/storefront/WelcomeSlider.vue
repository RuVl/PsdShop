<script setup>
import {computed, onBeforeUnmount, onMounted, ref} from 'vue';
import {useContentStore} from '@/stores/content.js';
import {useLocalized} from '@/composables/localized.js';

// The welcome slider from design/index.html, without swiper: one visible slide, the design's
// arrow styles (.swiper-button-prev/next in style.css), auto-advance that pauses on hover.
const contentStore = useContentStore();
const localized = useLocalized();
contentStore.loadSlides();

const slides = computed(() => contentStore.slides);
const current = ref(0);

function go(step) {
    const total = slides.value.length;
    if (total) current.value = (current.value + step + total) % total;
}

let timer = null;
const start = () => { timer ||= setInterval(() => go(1), 7000); };
const stop = () => { clearInterval(timer); timer = null; };
onMounted(start);
onBeforeUnmount(stop);
</script>

<template>
  <section v-if="slides.length" class="welcome" id="welcome">
    <div class="container">
      <div class="swiper slider-welcome" @mouseenter="stop" @mouseleave="start">
        <div class="slider-welcome-angle-left"></div>
        <div class="slider-welcome-angle-right"></div>
        <div class="swiper-wrapper">
          <div v-for="(slide, index) in slides" :key="index" v-show="index === current" class="swiper-slide">
            <div class="content">
              <div class="content__block">
                <div class="content__title title white">{{ localized(slide, 'title') }}</div>
                <div v-if="localized(slide, 'text')" class="idesc content__text text white">
                  <p>{{ localized(slide, 'text') }}</p>
                </div>
                <a v-if="localized(slide, 'button_label') && slide.button_url" class="btn btn-grade text white opacity"
                   :href="slide.button_url">{{ localized(slide, 'button_label') }}</a>
              </div>
              <picture v-if="slide.image" class="content__img"><img :src="slide.image" alt=""></picture>
            </div>
          </div>
        </div>
        <template v-if="slides.length > 1">
          <div class="swiper-button-prev" role="button" aria-label="Previous slide" @click="go(-1)"></div>
          <div class="swiper-button-next" role="button" aria-label="Next slide" @click="go(1)"></div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* swiper-bundle.css is not shipped; the minimal layout its classes relied on lives here. */
.swiper {
  position: relative;
  overflow: hidden;
}

.swiper-button-prev,
.swiper-button-next {
  cursor: pointer;
}
</style>
