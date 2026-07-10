# ProGuard/R8 rules for the AstralDeep Android client.
#
# Release builds currently ship with minification OFF (see app/build.gradle.kts:
# release { isMinifyEnabled = false }), so these rules are not applied today. They
# exist so the proguardFiles(...) reference resolves and to document the keeps we
# would need the moment shrinking is enabled.

# kotlinx.serialization: keep @Serializable classes' generated serializers.
-keepclassmembers,allowshrinking,allowobfuscation class kotlinx.serialization.** { *; }
-keep,includedescriptorclasses class com.personalailabs.astraldeep.**$$serializer { *; }
-keepclassmembers class com.personalailabs.astraldeep.** {
    *** Companion;
}

# OkHttp / Okio ship their own consumer rules; keep platform-optional warnings quiet.
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn org.conscrypt.**

# AppAuth (net.openid.appauth) uses reflection over its request/response models.
-keep class net.openid.appauth.** { *; }
