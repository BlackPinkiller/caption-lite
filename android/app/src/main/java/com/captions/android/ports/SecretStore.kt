package com.captions.android.ports

interface SecretStore {
    fun read(name: String): String
    fun write(name: String, value: String)
}
