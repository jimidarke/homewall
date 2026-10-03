package io.haku.tablet.ui.backdrop

import kotlin.random.Random

/**
 * Deals [items] in shuffled rounds: every item once per round, and never the same item twice in a row,
 * even across a round boundary (a single item is the exception). Not thread-safe: one loader owns it.
 */
class ShuffleBag<T>(private val random: Random) {
    private var items: List<T> = emptyList()
    private val queue = ArrayDeque<T>()
    private var last: T? = null

    val isEmpty: Boolean get() = items.isEmpty()

    /**
     * Swaps in a fresh listing. The same set in any order keeps the current round going; a different set
     * starts a new round, so a removed item is never dealt and a new one gets its turn soon.
     */
    fun reset(newItems: List<T>) {
        if (newItems.toSet() == items.toSet()) return
        items = newItems
        queue.clear()
    }

    /** The next item, or null while empty. */
    fun next(): T? {
        if (items.isEmpty()) return null
        if (queue.isEmpty()) {
            val round = items.shuffled(random).toMutableList()
            if (round.size > 1 && round.first() == last) round.add(round.removeAt(0))
            queue.addAll(round)
        }
        return queue.removeFirst().also { last = it }
    }
}
