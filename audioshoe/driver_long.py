# from Claude AI

import torch
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import librosa

# Load model and processor
model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-base")
processor = WhisperProcessor.from_pretrained("openai/whisper-base")

# Load audio file
audio, sr = librosa.load("your_audio_file.wav", sr=16000)

# Process audio in chunks (adjust chunk_length as needed)
chunk_length = 30  # seconds
stride_length = 15  # seconds
chunk_len_samples = chunk_length * sr
stride_len_samples = stride_length * sr

results = []

for i in range(0, len(audio), stride_len_samples):
    chunk = audio[i:i+chunk_len_samples]
    input_features = processor(chunk, sampling_rate=sr, return_tensors="pt").input_features

    # Generate with detailed output
    with torch.no_grad():
        outputs = model.generate(
            input_features,
            return_dict_in_generate=True,
            output_scores=True,
            max_length=448
        )

    # Decode the output
    transcription = processor.batch_decode(outputs.sequences, skip_special_tokens=True)

    # Get logprobs and process tokens
    logprobs = torch.stack(outputs.scores, dim=1).softmax(-1)
    tokens = outputs.sequences[0].tolist()

    # Process tokens to get word-level information
    words = []
    current_word = ""
    current_logprob = 0
    current_start_time = i / sr  # Start time of the current chunk

    for j, token in enumerate(tokens):
        if token in processor.tokenizer.all_special_ids:
            continue
        
        word = processor.tokenizer.decode([token])
        prob = logprobs[0][j][token].item()
        
        if word.startswith(" ") and current_word:
            words.append({
                "word": current_word.strip(),
                "logprob": current_logprob,
                "start_time": current_start_time
            })
            current_word = word
            current_logprob = prob
            current_start_time = i / sr + (j / len(tokens)) * chunk_length
        else:
            current_word += word
            current_logprob += prob

    if current_word:
        words.append({
            "word": current_word.strip(),
            "logprob": current_logprob,
            "start_time": current_start_time
        })

    results.extend(words)

# Print results
for word_info in results:
    print(f"Word: {word_info['word']}, LogProb: {word_info['logprob']:.4f}, Start Time: {word_info['start_time']:.2f}s")
