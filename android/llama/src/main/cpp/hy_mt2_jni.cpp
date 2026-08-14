#include <jni.h>
#include <android/log.h>

#include <string>
#include <vector>

#include "llama.h"
#include "common.h"
#include "sampling.h"
#include "chat.h"

#define LOG_TAG "HyMt2"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Official HyMT2 inference parameters for the 1.8B/7B models.
static constexpr float HYMT2_TEMP          = 0.7f;
static constexpr float HYMT2_TOP_P         = 0.6f;
static constexpr int   HYMT2_TOP_K         = 20;
static constexpr float HYMT2_REP_PENALTY   = 1.05f;
static constexpr int   DEFAULT_N_CTX       = 1024;

static llama_model   * g_model   = nullptr;
static llama_context * g_context = nullptr;

static void llama_log_callback(enum ggml_log_level level, const char * text, void * /*user_data*/) {
    if (text == nullptr) {
        return;
    }
    if (level <= GGML_LOG_LEVEL_WARN) {
        __android_log_write(ANDROID_LOG_WARN, "HyMt2LLM", text);
    } else {
        __android_log_write(ANDROID_LOG_INFO, "HyMt2LLM", text);
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_captions_android_hymt_HyMt2Engine_nativeLoad(
    JNIEnv * env,
    jobject /*unused*/,
    jstring model_path,
    jint    n_ctx,
    jint    n_threads) {
    if (g_model != nullptr) {
        llama_free(g_context);
        llama_free_model(g_model);
        g_model = nullptr;
        g_context = nullptr;
    }

    const char * path = env->GetStringUTFChars(model_path, nullptr);

    llama_log_set(llama_log_callback, nullptr);
    llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers = 0; // CPU only
    mparams.load_mode = LLAMA_LOAD_MODE_MMAP;
    g_model = llama_model_load_from_file(path, mparams);
    env->ReleaseStringUTFChars(model_path, path);
    if (g_model == nullptr) {
        LOGE("failed to load model");
        return JNI_FALSE;
    }

    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = n_ctx > 0 ? n_ctx : DEFAULT_N_CTX;
    cparams.n_threads = n_threads > 0 ? n_threads : 4;
    cparams.n_threads_batch = cparams.n_threads;
    g_context = llama_init_from_model(g_model, cparams);
    if (g_context == nullptr) {
        LOGE("failed to init context");
        llama_free_model(g_model);
        g_model = nullptr;
        return JNI_FALSE;
    }

    LOGI("model loaded, n_ctx = %d, n_threads = %d", cparams.n_ctx, cparams.n_threads);
    return JNI_TRUE;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_captions_android_hymt_HyMt2Engine_nativeGenerate(
    JNIEnv * env,
    jobject /*unused*/,
    jstring prompt,
    jint    max_tokens) {
    if (g_model == nullptr || g_context == nullptr) {
        return env->NewStringUTF("");
    }

    // Each translation starts from a fresh sequence. Without clearing the KV
    // cache, a new (shorter) prompt would decode over stale positions left by
    // the previous generation and produce garbage output.
    llama_memory_clear(llama_get_memory(g_context), true);

    const char * prompt_c = env->GetStringUTFChars(prompt, nullptr);
    std::string prompt_str(prompt_c);
    env->ReleaseStringUTFChars(prompt, prompt_c);

    // Apply the model's chat template as a single user message.
    auto chat_templates = common_chat_templates_init(g_model, "");
    std::string formatted = prompt_str;
    if (common_chat_templates_was_explicit(chat_templates.get())) {
        common_chat_templates_inputs inputs;
        common_chat_msg msg;
        msg.role = "user";
        msg.content = prompt_str;
        inputs.messages.push_back(msg);
        formatted = common_chat_templates_apply(chat_templates.get(), inputs).prompt;
        if (formatted.empty()) {
            formatted = prompt_str;
        }
    }

    auto tokens = common_tokenize(g_context, formatted, true, true);

    llama_batch batch = llama_batch_get_one(tokens.data(), static_cast<int32_t>(tokens.size()));
    if (llama_decode(g_context, batch) != 0) {
        LOGE("llama_decode failed for prompt");
        return env->NewStringUTF("");
    }

    common_params_sampling sparams;
    sparams.temp           = HYMT2_TEMP;
    sparams.top_p          = HYMT2_TOP_P;
    sparams.top_k          = HYMT2_TOP_K;
    sparams.penalty_repeat = HYMT2_REP_PENALTY;
    auto * sampler = common_sampler_init(g_model, sparams);

    std::string result;
    const llama_token eos = llama_vocab_eos(llama_model_get_vocab(g_model));
    const int limit = max_tokens > 0 ? max_tokens : 256;

    for (int i = 0; i < limit; i++) {
        const llama_token id = common_sampler_sample(sampler, g_context, -1);
        common_sampler_accept(sampler, id, true);
        if (id == eos) {
            break;
        }
        result += common_token_to_piece(g_context, id);

        llama_token token = id;
        llama_batch next = llama_batch_get_one(&token, 1);
        if (llama_decode(g_context, next) != 0) {
            LOGE("llama_decode failed during generation");
            break;
        }
    }
    common_sampler_free(sampler);

    return env->NewStringUTF(result.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_captions_android_hymt_HyMt2Engine_nativeUnload(
    JNIEnv * /*env*/,
    jobject /*unused*/) {
    if (g_context != nullptr) {
        llama_free(g_context);
        g_context = nullptr;
    }
    if (g_model != nullptr) {
        llama_free_model(g_model);
        g_model = nullptr;
    }
    LOGI("model unloaded");
}
