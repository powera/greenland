# based from README for whisper

# intended to run a single regression test of speech2txt
import torch
import librosa
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

model_id = "openai/whisper-large-v3-turbo"

# Always use MacBook M3 settings
device = torch.device("mps")
torch_dtype = torch.float16 if (model_id == "openai/whisper-large-v3-turbo") else torch.float32

model_dir = "/Users/powera/repo/whisper_turbo"
model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_dir, torch_dtype=torch_dtype, low_cpu_mem_usage=True
)
model.to(device)

processor = AutoProcessor.from_pretrained(model_dir)

pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    torch_dtype=torch_dtype,
    device=device,
)

audio_path = "/Users/powera/repo/greenland/audioshoe/sample/test.mp3"
audio_data, sample_rate = librosa.load(audio_path, sr=None)

result = pipe({"array": audio_data, "sampling_rate": sample_rate})
print(result["text"])
