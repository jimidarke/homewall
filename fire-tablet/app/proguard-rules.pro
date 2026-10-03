# R8 rules for the release build.
#
# kotlinx.serialization 1.7.3 bundles its common rules in the jar
# (META-INF/com.android.tools/r8/kotlinx-serialization-*.pro): they keep the `Companion` field and
# `serializer()` of every retained @Serializable class. The block below is the library README's
# per-package addition, scoped to this app's models, so a serializer is never stripped or renamed
# even if a future lookup goes by class (serializer<T>()) rather than the direct `X.serializer()`
# calls used today. A missing rule shows up at runtime as "Serializer for class ... not found".
-keep,includedescriptorclasses class io.haku.tablet.data.**$$serializer { *; }
-keepclassmembers class io.haku.tablet.data.** {
    *** Companion;
}
-keepclasseswithmembers class io.haku.tablet.data.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp 4.12 ships its own consumer rules (META-INF/proguard/okhttp3.pro); nothing to add here.
