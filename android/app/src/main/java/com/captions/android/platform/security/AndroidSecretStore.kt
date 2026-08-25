package com.captions.android.platform.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.captions.android.ports.SecretStore
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class AndroidSecretStore(context: Context) : SecretStore {
    private val preferences = context.applicationContext.getSharedPreferences(
        PREFERENCES,
        Context.MODE_PRIVATE,
    )

    override fun read(name: String): String {
        val encoded = preferences.getString(name, null) ?: return ""
        return runCatching {
            val (iv, encrypted) = encoded.split(SEPARATOR, limit = 2)
            val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                init(
                    Cipher.DECRYPT_MODE,
                    secretKey(),
                    GCMParameterSpec(TAG_LENGTH_BITS, Base64.decode(iv, Base64.NO_WRAP)),
                )
            }
            cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)).toString(Charsets.UTF_8)
        }.getOrDefault("")
    }

    override fun write(name: String, value: String) {
        if (value.isBlank()) {
            preferences.edit().remove(name).apply()
            return
        }
        val cipher = Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.ENCRYPT_MODE, secretKey())
        }
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val encoded = listOf(cipher.iv, encrypted)
            .joinToString(SEPARATOR) { Base64.encodeToString(it, Base64.NO_WRAP) }
        preferences.edit().putString(name, encoded).apply()
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE).run {
            init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .build(),
            )
            generateKey()
        }
    }

    private companion object {
        const val PREFERENCES = "captions_secrets"
        const val KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "captions-api-secrets"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val TAG_LENGTH_BITS = 128
        const val SEPARATOR = "."
    }
}
