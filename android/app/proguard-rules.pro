# Keep this file intentionally small. Add rules only when a concrete native
# adapter requires them.

# HyMt2Engine and sherpa-onnx expose JNI entry points by name; minification
# must not rename the classes or their native methods.
-keepclasseswithmembernames,includedescriptorclasses class * {
    native <methods>;
}
