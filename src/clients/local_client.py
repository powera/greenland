#!/usr/bin/python3

""" Runs a "transformers" LLM model locally."""

import asyncio
import gc
import os

from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch


async def text_completion(prompt, model_dir):
    """
    Run text completion with a local LLM model.

    Args:
        prompt: Text prompt for completion
        model_dir: Path to the model directory
    """
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        torch_dtype=torch.float16,
    )
    model.to("mps")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    loop = asyncio.get_event_loop()

    with torch.no_grad():
        input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to("mps")
        output = await loop.run_in_executor(
            None,
            lambda: model.generate(
                input_ids,
                max_length=192,
                repetition_penalty=1.5,
                temperature=0.2,
                top_p=0.9,
                num_beams=4,
            ),
        )
    response = tokenizer.decode(output[0], skip_special_tokens=True)
    return response


async def text_chat(prompt, model_dir):
    """
    Run text chat with a local instruction-tuned LLM model.

    Args:
        prompt: Text prompt for chat
        model_dir: Path to the instruction-tuned model directory
    """
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        torch_dtype=torch.float16,
    )
    model.to("mps")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    loop = asyncio.get_event_loop()

    with torch.no_grad():
        messages = [{"role": "user", "content": prompt}]
        input_text = tokenizer.apply_chat_template(messages, tokenize=False)
        input_ids = tokenizer.encode(input_text, return_tensors="pt").to("mps")
        output = await loop.run_in_executor(
            None,
            lambda: model.generate(
                input_ids,
                max_new_tokens=250,
                repetition_penalty=1.5,
                temperature=0.2,
                top_p=0.9,
                do_sample=True,
            ),
        )
    response = tokenizer.decode(output[0], skip_special_tokens=True)
    return response


def text_completion_interactive(prompt, model_dir):
    """
    Run interactive text completion with a local LLM model (token-by-token generation).

    Args:
        prompt: Text prompt for completion
        model_dir: Path to the model directory
    """
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
    )
    model.to("mps")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    with torch.no_grad():
        input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to("mps")
        generated_ids = input_ids
        past_key_values = None

        for _ in range(32):
            # Forward pass to get logits
            outputs = model(
                input_ids=generated_ids, past_key_values=past_key_values, use_cache=True
            )
            logits = outputs.logits
            past_key_values = outputs.past_key_values  # Cache key-values for efficiency

            # Use top_k
            top_k_values, top_k_indices = torch.topk(
                torch.log_softmax(logits[:, -1, :], dim=-1), 12, dim=-1
            )
            top_k_logprobs = torch.exp(top_k_values).squeeze().tolist()
            top_k_words = tokenizer.convert_ids_to_tokens(top_k_indices.squeeze().tolist())

            print(top_k_words)
            print(top_k_logprobs)
            print("  ")

            if top_k_logprobs[0] > 0.4:
                idx = 0
            else:
                idx = 1
            next_token_id = torch.tensor([[top_k_indices[0][idx]]]).to("mps")
            generated_ids = torch.cat([generated_ids, next_token_id], dim=-1)

            # Stop if EOS token is generated
            if next_token_id.item() == tokenizer.eos_token_id:
                break

    response = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
    return response


def text_chat_interactive(prompt, model_dir):
    """
    Run interactive text chat with a local instruction-tuned LLM model (token-by-token generation).

    Args:
        prompt: Text prompt for chat
        model_dir: Path to the instruction-tuned model directory
    """
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        torch_dtype=torch.float16,
    )
    model.to("mps")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    with torch.no_grad():
        messages = [{"role": "user", "content": prompt}]
        input_text = tokenizer.apply_chat_template(messages, tokenize=False)
        input_ids = tokenizer.encode(input_text, return_tensors="pt").to("mps")
        generated_ids = input_ids
        past_key_values = None

        for _ in range(64):
            # Forward pass to get logits
            outputs = model(
                input_ids=generated_ids, past_key_values=past_key_values, use_cache=True
            )
            logits = outputs.logits
            past_key_values = outputs.past_key_values  # Cache key-values for efficiency

            # Use top_k
            top_k_values, top_k_indices = torch.topk(
                torch.log_softmax(logits[:, -1, :], dim=-1), 18, dim=-1
            )
            top_k_logprobs = torch.exp(top_k_values).squeeze().tolist()
            top_k_words = tokenizer.convert_ids_to_tokens(top_k_indices.squeeze().tolist())

            print(top_k_words)
            print(top_k_logprobs)
            print("  ")

            if top_k_logprobs[0] > 0.7:
                idx = 0
            elif top_k_indices[0][1].item() != tokenizer.eos_token_id and top_k_logprobs[1] > 0.05:
                idx = 1
            else:
                idx = 2
            next_token_id = torch.tensor([[top_k_indices[0][idx]]]).to("mps")
            generated_ids = torch.cat([generated_ids, next_token_id], dim=-1)

            # Stop if EOS token is generated
            if next_token_id.item() == tokenizer.eos_token_id:
                break

    response = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
    return response
