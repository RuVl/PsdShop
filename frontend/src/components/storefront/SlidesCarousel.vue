<script setup>
import {computed, onBeforeUnmount, onMounted, ref} from 'vue';
import {useContentStore} from '@/stores/content.js';

// The welcome slider from design/index.html, without swiper: one visible slide, the design's
// arrow styles (.swiper-button-prev/next in style.css), auto-advance that pauses on hover.
const contentStore = useContentStore();
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
                <div class="content__title title white">{{ slide.title }}</div>
                <div v-if="slide.text" class="idesc content__text text white">
                  <p>{{ slide.text }}</p>
                </div>
                <a v-if="slide.button_label && slide.button_url" class="btn btn-big btn-ghost btn-ghost--light"
                   :href="slide.button_url">{{ slide.button_label }}</a>
              </div>
              <picture v-if="slide.image" class="content__img"><img :src="slide.image" alt=""></picture>
            </div>
          </div>
        </div>
        <template v-if="slides.length > 1">
          <button class="swiper-button-prev btn-reset" type="button" aria-label="Previous slide" @click="go(-1)">
            <svg viewBox="0 0 12 20" aria-hidden="true"><path d="M10.5 1.5 2 10l8.5 8.5" fill="none"
                 stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button class="swiper-button-next btn-reset" type="button" aria-label="Next slide" @click="go(1)">
            <svg viewBox="0 0 12 20" aria-hidden="true"><path d="M1.5 1.5 10 10l-8.5 8.5" fill="none"
                 stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <div class="slider-welcome-dots">
            <button v-for="(slide, index) in slides" :key="index" class="btn-reset slider-welcome-dot"
                    :class="{current: index === current}" type="button" :aria-label="`Slide ${index + 1}`"
                    @click="current = index"></button>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* swiper-bundle.css is not shipped, and style.css only dresses these arrows - size, background,
   `top` - assuming swiper had already positioned them. Everything it took for granted lives here,
   including the chevron itself: the design drew it with the swiper-icons font. */
.swiper {
  position: relative;
  overflow: hidden;
}

.swiper-button-prev,
.swiper-button-next {
  position: absolute;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #fff;
  border: 0;
  cursor: pointer;
}

.swiper-button-prev svg,
.swiper-button-next svg {
  width: 12px;
  height: 20px;
}

/* The design's slides carry no button and no dots. Room for both is made in the text column
   alone: .content__img is bottom-aligned, so padding on .content itself lifted the picture off
   the bottom edge of the slide - which is exactly what it must not do. */
.content__block {
  padding-bottom: 26px;
}

/* Over the slide, not under it, and inside .content's own 101px padding so the dots never land
   on the picture on the right. */
.slider-welcome-dots {
  position: absolute;
  left: 101px;
  bottom: 14px;
  z-index: 2;
  display: flex;
  gap: 8px;
}

/* Below 880px .content stacks and centres itself; the dots follow it. */
@media (max-width: 880px) {
  .slider-welcome-dots {
    left: 0;
    right: 0;
    justify-content: center;
  }
}

.slider-welcome-dot {
  width: 8px;
  height: 8px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, .45);
  cursor: pointer;
  transition: background .3s, transform .3s;
}

.slider-welcome-dot.current {
  background: #fff;
  transform: scale(1.3);
}

/* The design hides the arrows on narrow screens - they would sit on top of the text. The dots
   are what is left to steer with there. */
@media (max-width: 470px) {
  .swiper-button-prev,
  .swiper-button-next {
    display: none;
  }

  .slider-welcome-dots {
    bottom: 10px;
  }
}
</style>
