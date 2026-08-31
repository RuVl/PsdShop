import {onBeforeUnmount, onMounted, readonly, ref} from 'vue';

// The header is `position: fixed` over a light page, so without a background it dissolves into the
// content as soon as anything scrolls under it. The design solves that in app.js: paint it black
// past the first pixel (`header-scrolled`) and slide it away while the reader moves down (`out`).

// Below this the header stays put: hiding it right under the top edge only flickers.
const HIDE_AFTER = 100;

/**
 * Tracks the page scroll for the header's two classes.
 *
 * @param {() => boolean} isPinned - true while the header must stay on screen (the mobile menu is
 *                                   open, and the menu *is* the header).
 * @returns {{scrolled: Readonly<import('vue').Ref<boolean>>, hidden: Readonly<import('vue').Ref<boolean>>}}
 */
export function useHeaderScroll(isPinned = () => false) {
    const scrolled = ref(false);
    const hidden = ref(false);

    let previousScroll = 0;
    // One read per frame: `scroll` fires far more often than the page repaints.
    let ticking = false;

    function measure() {
        const current = Math.round(window.scrollY);
        scrolled.value = current > 0;
        hidden.value = !isPinned() && current > HIDE_AFTER && current > previousScroll;
        previousScroll = current;
        ticking = false;
    }

    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(measure);
    }

    onMounted(() => {
        measure();
        window.addEventListener('scroll', onScroll, {passive: true});
    });
    onBeforeUnmount(() => window.removeEventListener('scroll', onScroll));

    return {scrolled: readonly(scrolled), hidden: readonly(hidden)};
}
