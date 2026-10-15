plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.jetbrains.kotlin.android)
    alias(libs.plugins.serialization)
}

android {
    namespace = "io.haku.tablet"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.haku.tablet"
        minSdk = 30          // Fire OS 8 (Fire 7 KFQUWI) is API 30
        targetSdk = 34
        versionCode = 6
        versionName = "1.1.0"

        // Sidecar base URL. The tablet is LAN-only (iot); nserver hosts haku-sidecar.
        buildConfigField("String", "SIDECAR_BASE", "\"http://192.0.2.20:1986\"")
        // Sent as ?layout= so the sidecar returns the tablet's grid and glyph/active/level tile keys.
        buildConfigField("String", "LAYOUT", "\"tablet\"")
    }

    buildTypes {
        release {
            // R8 for the wall build. Signed with the debug key (one device, no Play Store), so `adb install -r`
            // swaps it with a debug install in place, with no uninstall.
            isMinifyEnabled = true
            isShrinkResources = true
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests {
            // Stub android.util.Log in JVM unit tests instead of throwing "not mocked".
            isReturnDefaultValues = true
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.material3)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}
