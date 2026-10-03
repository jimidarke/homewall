package io.haku.tablet.data

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.floatOrNull
import kotlinx.serialization.json.longOrNull

/*
 * Tolerant reads off a JsonObject: a missing key or the wrong JSON type is a default or null, never a throw.
 * (HubState keeps its own private copies of the first few.)
 */

/** The string at [k], or null for a missing key, `null`, an object or an array. Numbers and booleans read as their text. */
internal fun JsonObject.strOrNull(k: String): String? = (this[k] as? JsonPrimitive)?.contentOrNull

internal fun JsonObject.str(k: String): String = strOrNull(k) ?: ""

/** True only for a JSON boolean `true`; the string "true", numbers and null are false. */
internal fun JsonObject.bool(k: String): Boolean =
    (this[k] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull ?: false

/** A JSON integer, or null for a missing key, a string, a fraction or anything non-numeric. */
internal fun JsonObject.long(k: String): Long? =
    (this[k] as? JsonPrimitive)?.takeIf { !it.isString }?.longOrNull

/** Like [long], saturated into the Int range so callers can clamp to their own bounds. */
internal fun JsonObject.int(k: String): Int? =
    long(k)?.coerceIn(Int.MIN_VALUE.toLong(), Int.MAX_VALUE.toLong())?.toInt()

/** A finite JSON number, or null for a missing key, a string, NaN, infinity or anything non-numeric. */
internal fun JsonObject.float(k: String): Float? = (this[k] as? JsonPrimitive)?.finiteFloatOrNull()

internal fun JsonObject.array(k: String): JsonArray? = this[k] as? JsonArray

internal fun JsonObject.obj(k: String): JsonObject? = this[k] as? JsonObject

/** This element as a finite number: a JSON string, boolean, `null`, NaN or infinity is not one. */
internal fun JsonPrimitive.finiteFloatOrNull(): Float? =
    if (isString) null else floatOrNull?.takeIf { it.isFinite() }
