import java.net.URI
import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.jetbrains.kotlin.android)
    alias(libs.plugins.serialization)
}

// The sidecar this build talks to: `haku.sidecarBase` in local.properties (gitignored), else
// $HAKU_SIDECAR_BASE, else a documentation address (fine for CI builds and unit tests).
val localProps = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
val sidecarBase: String = (localProps.getProperty("haku.sidecarBase")
    ?: System.getenv("HAKU_SIDECAR_BASE") ?: "http://192.0.2.20:1986").trimEnd('/')

android {
    namespace = "io.haku.tablet"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.haku.tablet"
        minSdk = 30          // Fire OS 8 (Fire 7 KFQUWI) is API 30
        targetSdk = 34
        versionCode = 7
        versionName = "1.1.1"

        // Sidecar base URL (see sidecarBase above). The tablet is LAN-only; nserver hosts haku-sidecar.
        buildConfigField("String", "SIDECAR_BASE", "\"$sidecarBase\"")
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

// Cleartext HTTP is allowed to the sidecar's host only (the sidecar on :1986 and the door
// camera's HLS on :1985); everything else stays HTTPS-only. Generated so the host comes
// from the same setting as SIDECAR_BASE instead of being committed.
abstract class NetworkSecurityConfigTask : DefaultTask() {
    @get:Input abstract val host: Property<String>
    @get:OutputDirectory abstract val outputDir: DirectoryProperty

    @TaskAction
    fun write() {
        val out = outputDir.file("xml/network_security_config.xml").get().asFile
        out.parentFile.mkdirs()
        out.writeText(
            """
            |<?xml version="1.0" encoding="utf-8"?>
            |<network-security-config>
            |    <domain-config cleartextTrafficPermitted="true">
            |        <domain includeSubdomains="false">${host.get()}</domain>
            |    </domain-config>
            |</network-security-config>
            |""".trimMargin()
        )
    }
}

val networkSecurityConfig = tasks.register<NetworkSecurityConfigTask>("generateNetworkSecurityConfig") {
    host.set(URI(sidecarBase).host)
    outputDir.set(layout.buildDirectory.dir("generated/haku/res"))
}

androidComponents {
    onVariants { variant ->
        variant.sources.res?.addGeneratedSourceDirectory(networkSecurityConfig, NetworkSecurityConfigTask::outputDir)
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
