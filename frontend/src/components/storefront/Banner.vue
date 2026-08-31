<script setup>
import {computed, onBeforeUnmount, onMounted, ref, watch} from 'vue';
import {useContentStore} from '@/stores/content.js';

// The welcome banner: the slides an admin writes, one at a time, with the same box the bot page
// prints stacked (storefront/catalog.html). Markup and styles are ours - `.banner` in shop.css -
// so nothing here depends on the mockup's swiper leftovers.
const INTERVAL = 7000;
const SWIPE_THRESHOLD = 40;

const contentStore = useContentStore();
contentStore.loadSlides();

const slides = computed(() => contentStore.slides);
const current = ref(0);
const paused = ref(false);
const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)');

function goTo(index) {
    const total = slides.value.length;
    if (total) current.value = (index + total) % total;
}

const go = (step) => goTo(current.value + step);

// One timer, restarted on every change: a click must not be followed by the leftover of the
// interval it interrupted.
let timer = null;

function stop() {
    clearTimeout(timer);
    timer = null;
}

function schedule() {
    stop();
    if (paused.value || reduceMotion?.matches || slides.value.length < 2 || document.hidden) return;
    timer = setTimeout(() => {
        go(1);
        schedule();
    }, INTERVAL);
}

watch([current, paused, slides], schedule);

// A tab in the background rotates through the whole banner unseen and comes back on a slide the
// reader never asked for.
const onVisibility = () => schedule();

onMounted(() => {
    document.addEventListener('visibilitychange', onVisibility);
    schedule();
});

onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibility);
    stop();
});

// Swipe: the pointer events cover touch and mouse drag alike, and a tap on a link is left alone
// because nothing moves until the threshold is passed.
let pointerStart = null;

function onPointerDown(event) {
    pointerStart = event.pointerType === 'mouse' ? null : event.clientX;
}

function onPointerUp(event) {
    if (pointerStart === null) return;
    const dx = event.clientX - pointerStart;
    pointerStart = null;
    if (Math.abs(dx) >= SWIPE_THRESHOLD) go(dx < 0 ? 1 : -1);
}
</script>

<template>
  <section v-if="slides.length" id="welcome" class="banner">
    <div class="container">
      <div class="banner__frame" role="group" aria-roledescription="carousel"
           :aria-label="$t('storefront.banner.label')"
           tabindex="-1"
           @mouseenter="paused = true" @mouseleave="paused = false"
           @focusin="paused = true" @focusout="paused = false"
           @keydown.left.prevent="go(-1)" @keydown.right.prevent="go(1)"
           @pointerdown="onPointerDown" @pointerup="onPointerUp" @pointercancel="pointerStart = null">
        <ul class="banner__track">
          <li v-for="(slide, index) in slides" :key="index" class="banner__slide"
              :class="{'is-current': index === current}" :inert="index !== current"
              :aria-hidden="index !== current">
            <div class="banner__body">
              <h2 class="banner__title">{{ slide.title }}</h2>
              <p v-if="slide.text" class="banner__text">{{ slide.text }}</p>
              <a v-if="slide.hasButton" class="banner__cta btn btn-big btn-ghost btn-ghost--light"
                 :href="slide.button_url">{{ slide.button_label }}</a>
            </div>
            <picture v-if="slide.image" class="banner__media">
              <img :src="slide.image" alt="" loading="lazy">
            </picture>
          </li>
        </ul>

        <template v-if="slides.length > 1">
          <button class="banner__arrow banner__arrow--prev" type="button"
                  :aria-label="$t('storefront.banner.previous')" @click="go(-1)">
            <svg viewBox="0 0 12 20" aria-hidden="true"><path d="M10.5 1.5 2 10l8.5 8.5" fill="none"
                 stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button class="banner__arrow banner__arrow--next" type="button"
                  :aria-label="$t('storefront.banner.next')" @click="go(1)">
            <svg viewBox="0 0 12 20" aria-hidden="true"><path d="M1.5 1.5 10 10l-8.5 8.5" fill="none"
                 stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <div class="banner__dots">
            <button v-for="(slide, index) in slides" :key="index" class="banner__dot" type="button"
                    :class="{'is-current': index === current}"
                    :aria-label="$t('storefront.banner.slide', {number: index + 1})"
                    :aria-current="index === current ? 'true' : undefined"
                    @click="goTo(index)"></button>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>
