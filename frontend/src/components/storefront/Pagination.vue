<script setup>
import {computed} from 'vue';

// Numbered pages, the same set the bot page renders at the same addresses (ADR-0010). Real links,
// so a middle click opens a page in a tab and a crawler walks them.
const props = defineProps({
    page: {type: Number, required: true},
    totalPages: {type: Number, required: true},
    // Builds the route for a page number - the view owns what else the address carries (`?q=`).
    to: {type: Function, required: true},
});

const ELLIPSIS = '…';

// First, last, and a window around the current page; the gaps become one ellipsis each. At 42
// pages that is nine slots instead of forty-two.
const items = computed(() => {
    const total = props.totalPages;
    const current = props.page;
    if (total <= 7) return Array.from({length: total}, (_, index) => index + 1);

    const window = new Set([1, total, current, current - 1, current + 1]);
    if (current <= 3) window.add(2).add(3).add(4);
    if (current >= total - 2) window.add(total - 1).add(total - 2).add(total - 3);

    const numbers = [...window].filter(number => number >= 1 && number <= total).sort((a, b) => a - b);
    return numbers.flatMap((number, index) => {
        const previous = numbers[index - 1];
        return previous && number - previous > 1 ? [ELLIPSIS, number] : [number];
    });
});
</script>

<template>
  <nav v-if="totalPages > 1" class="pagination" :aria-label="$t('pagination.label')">
    <router-link v-if="page > 1" class="btn btn-ghost pagination__step" :to="to(page - 1)"
                 :aria-label="$t('pagination.previous')" rel="prev">‹</router-link>

    <template v-for="(item, index) in items" :key="`${item}-${index}`">
      <span v-if="item === '…'" class="pagination__gap" aria-hidden="true">…</span>
      <router-link v-else class="btn pagination__page" :class="item === page ? 'btn-solid' : 'btn-ghost'"
                   :to="to(item)" :aria-current="item === page ? 'page' : undefined">{{ item }}</router-link>
    </template>

    <router-link v-if="page < totalPages" class="btn btn-ghost pagination__step" :to="to(page + 1)"
                 :aria-label="$t('pagination.next')" rel="next">›</router-link>
  </nav>
</template>
