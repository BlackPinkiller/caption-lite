#include <jni.h>
#include <android/log.h>

#include <chrono>
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
static common_chat_templates_ptr g_chat_templates;
// Tokens of the last processed prompt, kept so the next generate only decodes
// the tokens that were not already in the KV cache (the template + subtitle
// context prefix is stable across translations).
static std::vector<llama_token> g_last_prompt;

static int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

static size_t common_prefix(const std::vector<llama_token> & a, const std::vector<llama_token> & b) {
    size_t n = std::min(a.size(), b.size());
    size_t i = 0;
    while (i < n && a[i] == b[i]) {
        i++;
    }
    return i;
}

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

    g_chat_templates = common_chat_templates_init(g_model, "");
    g_last_prompt.clear();

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

    const int64_t t0 = now_ms();

    const char * prompt_c = env->GetStringUTFChars(prompt, nullptr);
    std::string prompt_str(prompt_c);
    env->ReleaseStringUTFChars(prompt, prompt_c);

    // Apply the model's chat template as a single user message.
    std::string formatted = prompt_str;
    if (g_chat_templates != nullptr && common_chat_templates_was_explicit(g_chat_templates.get())) {
        common_chat_templates_inputs inputs;
        common_chat_msg msg;
        msg.role = "user";
        msg.content = prompt_str;
        inputs.messages.push_back(msg);
        formatted = common_chat_templates_apply(g_chat_templates.get(), inputs).prompt;
        if (formatted.empty()) {
            formatted = prompt_str;
        }
    }

    auto tokens = common_tokenize(g_context, formatted, true, true);

    // Reuse the KV cache across calls: the template + context prefix is stable,
    // so only the new suffix tokens need a decode. A metadata-only clear resets
    // the sequence when the prompt has no common prefix with the previous one.
    llama_memory_t mem = llama_get_memory(g_context);
    size_t start = 0;
    if (!g_last_prompt.empty()) {
        size_t shared = common_prefix(g_last_prompt, tokens);
        if (shared >= tokens.size()) {
            shared = tokens.size() - 1; // always decode at least the last token for fresh logits
        }
        if (shared > 0) {
            if (llama_memory_seq_rm(mem, 0, static_cast<llama_pos>(shared), -1)) {
                start = shared;
            } else {
                llama_memory_clear(mem, false);
            }
        } else {
            llama_memory_clear(mem, false);
        }
    } else {
        llama_memory_clear(mem, false);
    }

    llama_batch batch = llama_batch_get_one(
        tokens.data() + start, static_cast<int32_t>(tokens.size() - start));
    if (llama_decode(g_context, batch) != 0) {
        LOGE("llama_decode failed for prompt");
        return env->NewStringUTF("");
    }
    g_last_prompt = tokens;
    const int64_t t1 = now_ms();

    common_params_sampling sparams;
    sparams.temp           = HYMT2_TEMP;
    sparams.top_p          = HYMT2_TOP_P;
    sparams.top_k          = HYMT2_TOP_K;
    sparams.penalty_repeat = HYMT2_REP_PENALTY;
    auto * sampler = common_sampler_init(g_model, sparams);

    const llama_vocab * vocab = llama_model_get_vocab(g_model);
    const int limit = max_tokens > 0 ? max_tokens : 256;

    std::string result;
    int generated = 0;
    bool stopped = false;
    for (int i = 0; i < limit; i++) {
        const llama_token id = common_sampler_sample(sampler, g_context, -1);
        common_sampler_accept(sampler, id, true);
        if (llama_vocab_is_eog(vocab, id)) {
            stopped = true;
            break;
        }
        result += common_token_to_piece(g_context, id);
        generated++;

        llama_token token = id;
        llama_batch next = llama_batch_get_one(&token, 1);
        if (llama_decode(g_context, next) != 0) {
            LOGE("llama_decode failed during generation");
            break;
        }
    }
    common_sampler_free(sampler);

    const int64_t t2 = now_ms();
    LOGI("generate: prompt_tokens=%zu decoded=%zu decode_ms=%lld gen_tokens=%d eog=%d "
         "gen_ms=%lld total_ms=%lld first_char=%.40s",
         tokens.size(), tokens.size() - start, (long long) (t1 - t0), generated, (int) stopped,
         (long long) (t2 - t1), (long long) (t2 - t0), result.c_str());

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
    g_chat_templates.reset();
    g_last_prompt.clear();
    LOGI("model unloaded");
}
