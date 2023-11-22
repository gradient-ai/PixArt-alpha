#!/usr/bin/env python

from __future__ import annotations

import os
import random
import uuid

import gradio as gr
import numpy as np
import PIL.Image
import torch

from diffusers import AutoencoderKL, PixArtAlphaPipeline

DESCRIPTION = """![Logo](https://raw.githubusercontent.com/PixArt-alpha/PixArt-alpha.github.io/master/static/images/logo.png)
        # PixArt-Alpha 1024px
        #### [PixArt-Alpha 1024px](https://github.com/PixArt-alpha/PixArt-alpha) is a transformer-based text-to-image diffusion system trained on text embeddings from T5. This demo uses the [PixArt-alpha/PixArt-XL-2-1024-MS](https://huggingface.co/PixArt-alpha/PixArt-XL-2-1024-MS) checkpoint.
        #### English prompts ONLY; 提示词仅限英文
        """

MAX_SEED = np.iinfo(np.int32).max
CACHE_EXAMPLES = torch.cuda.is_available() and os.getenv("CACHE_EXAMPLES", "1") == "1"
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE", "1024"))
USE_TORCH_COMPILE = os.getenv("USE_TORCH_COMPILE", "0") == "1"
ENABLE_CPU_OFFLOAD = os.getenv("ENABLE_CPU_OFFLOAD", "0") == "1"

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

style_list = [
    {
        "name": "(No style)",
        "prompt": "{prompt}",
        "negative_prompt": "",
    },
    {
        "name": "Cinematic",
        "prompt": "cinematic still {prompt} . emotional, harmonious, vignette, highly detailed, high budget, bokeh, cinemascope, moody, epic, gorgeous, film grain, grainy",
        "negative_prompt": "anime, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured",
    },
    {
        "name": "Photographic",
        "prompt": "cinematic photo {prompt} . 35mm photograph, film, bokeh, professional, 4k, highly detailed",
        "negative_prompt": "drawing, painting, crayon, sketch, graphite, impressionist, noisy, blurry, soft, deformed, ugly",
    },
    {
        "name": "Anime",
        "prompt": "anime artwork {prompt} . anime style, key visual, vibrant, studio anime,  highly detailed",
        "negative_prompt": "photo, deformed, black and white, realism, disfigured, low contrast",
    },
    {
        "name": "Manga",
        "prompt": "manga style {prompt} . vibrant, high-energy, detailed, iconic, Japanese comic style",
        "negative_prompt": "ugly, deformed, noisy, blurry, low contrast, realism, photorealistic, Western comic style",
    },
    {
        "name": "Digital Art",
        "prompt": "concept art {prompt} . digital artwork, illustrative, painterly, matte painting, highly detailed",
        "negative_prompt": "photo, photorealistic, realism, ugly",
    },
    {
        "name": "Pixel art",
        "prompt": "pixel-art {prompt} . low-res, blocky, pixel art style, 8-bit graphics",
        "negative_prompt": "sloppy, messy, blurry, noisy, highly detailed, ultra textured, photo, realistic",
    },
    {
        "name": "Fantasy art",
        "prompt": "ethereal fantasy concept art of  {prompt} . magnificent, celestial, ethereal, painterly, epic, majestic, magical, fantasy art, cover art, dreamy",
        "negative_prompt": "photographic, realistic, realism, 35mm film, dslr, cropped, frame, text, deformed, glitch, noise, noisy, off-center, deformed, cross-eyed, closed eyes, bad anatomy, ugly, disfigured, sloppy, duplicate, mutated, black and white",
    },
    {
        "name": "Neonpunk",
        "prompt": "neonpunk style {prompt} . cyberpunk, vaporwave, neon, vibes, vibrant, stunningly beautiful, crisp, detailed, sleek, ultramodern, magenta highlights, dark purple shadows, high contrast, cinematic, ultra detailed, intricate, professional",
        "negative_prompt": "painting, drawing, illustration, glitch, deformed, mutated, cross-eyed, ugly, disfigured",
    },
    {
        "name": "3D Model",
        "prompt": "professional 3d model {prompt} . octane render, highly detailed, volumetric, dramatic lighting",
        "negative_prompt": "ugly, deformed, noisy, low poly, blurry, painting",
    },
]

styles = {k["name"]: (k["prompt"], k["negative_prompt"]) for k in style_list}
STYLE_NAMES = list(styles.keys())
DEFAULT_STYLE_NAME = "(No style)"


def apply_style(style_name: str, positive: str, negative: str = "") -> Tuple[str, str]:
    p, n = styles.get(style_name, styles[DEFAULT_STYLE_NAME])
    if not negative:
        negative = ""
    return p.replace("{prompt}", positive), n + negative


if torch.cuda.is_available():
    pipe = PixArtAlphaPipeline.from_pretrained(
        "PixArt-alpha/PixArt-XL-2-1024-MS",
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )

    if ENABLE_CPU_OFFLOAD:
        pipe.enable_model_cpu_offload()
    else:
        pipe.to(device)
        print("Loaded on Device!")

    # speed-up T5
    pipe.text_encoder.to_bettertransformer()

    if USE_TORCH_COMPILE:
        pipe.transformer = torch.compile(
            pipe.transformer, mode="reduce-overhead", fullgraph=True
        )
        print("Model Compiled!")

        
import os
def save_image(img):
    unique_name = "outputs/session/"+str(uuid.uuid4()) + ".png"
    img.save(unique_name)
    return unique_name
# def save_image(imgs, batch):
#     if len(os.listdir('outputs/session/')) != 0:
#         for i in os.listdir('outputs/session/'):
#             os.rename('outputs/session/'+i, 'outputs/old/'+i)
#     unique_names = []
#     for i in range(batch):
#         unique_names.append("outputs/"+str(uuid.uuid4()) + ".png")
    
#     for unique_name in unique_names:
#         for img in imgs:
#             img.save(unique_name)
#         break
#     return "outputs/session/"


def randomize_seed_fn(seed: int, randomize_seed: bool) -> int:
    if randomize_seed:
        seed = random.randint(0, MAX_SEED)
    return seed


def generate(
    prompt: str,
    batch: int = 1,
    negative_prompt: str = "",
    style: str = DEFAULT_STYLE_NAME,
    use_negative_prompt: bool = False,
    seed: int = 0,
    width: int = 1024,
    height: int = 1024,
    guidance_scale: float = 4.5,
    num_inference_steps: int = 20,
    randomize_seed: bool = False,
    progress=gr.Progress(track_tqdm=True),
):
    seed = randomize_seed_fn(seed, randomize_seed)
    generator = torch.Generator().manual_seed(seed)

    if not use_negative_prompt:
        negative_prompt = None  # type: ignore
    prompt, negative_prompt = apply_style(style, prompt, negative_prompt)
    images =[]
    for i in range(batch):
        images.append(pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        guidance_scale=guidance_scale,
        num_inference_steps=num_inference_steps,
        generator=generator,
        output_type="pil",
        ).images[0])
        
    if len(os.listdir('outputs/session/')) != 0:
        for i in os.listdir('outputs/session/'):
            os.rename('outputs/session/'+i, 'outputs/old/'+i)
    for image in images:
        image_path = save_image(image)
        print(image_path)
    lst =[]
    for i in os.listdir('outputs/session/'):
        lst.append('outputs/session/'+i)
    return lst, seed


examples = [
    "A small cactus with a happy face in the Sahara desert.",
    "Pirate ship trapped in a cosmic maelstrom nebula, rendered in cosmic beach whirlpool engine, volumetric lighting, spectacular, ambient lights, light pollution, cinematic atmosphere, art nouveau style, illustration art artwork by SenseiJaye, intricate detail.",
    "stars, water, brilliantly, gorgeous large scale scene, a little girl, in the style of dreamy realism, light gold and amber, blue and pink, brilliantly illuminated in the background.",
    "3d digital art of an adorable ghost, glowing within, holding a heart shaped pumpkin, Halloween, super cute, spooky haunted house background",
    "beautiful lady, freckles, big smile, blue eyes, short ginger hair, dark makeup, wearing a floral blue vest top, soft light, dark grey background",
    "professional portrait photo of an anthropomorphic cat wearing fancy gentleman hat and jacket walking in autumn forest.",
    "an astronaut sitting in a diner, eating fries, cinematic, analog film",
    "Albert Einstein in a surrealist Cyberpunk 2077 world, hyperrealistic",
]

with gr.Blocks(css="style.css") as demo:
    gr.Markdown(DESCRIPTION)
    gr.DuplicateButton(
        value="Duplicate Space for private use",
        elem_id="duplicate-button",
        visible=os.getenv("SHOW_DUPLICATE_BUTTON") == "1",
    )
    with gr.Group():
        with gr.Row():
            with gr.Column():
                prompt = gr.Text(
                label="Prompt",
                show_label=False,
                max_lines=1,
                placeholder="Enter your prompt",
                container=False,
                )
                batch = gr.Slider(minimum = 1, maximum = 8, step = 1, value = 1, label = 'Batch Size (number of images to generate)')
            run_button = gr.Button("Run", scale=0)
        result = gr.Gallery(label="Result", show_label=False)
    with gr.Accordion("Advanced options", open=False):
        with gr.Row():
            use_negative_prompt = gr.Checkbox(label="Use negative prompt", value=False)
        style_selection = gr.Radio(
            show_label=True,
            container=True,
            interactive=True,
            choices=STYLE_NAMES,
            value=DEFAULT_STYLE_NAME,
            label="Image Style",
        )
        negative_prompt = gr.Text(
            label="Negative prompt",
            max_lines=1,
            placeholder="Enter a negative prompt",
            visible=False,
        )
        seed = gr.Slider(
            label="Seed",
            minimum=0,
            maximum=MAX_SEED,
            step=1,
            value=0,
        )
        randomize_seed = gr.Checkbox(label="Randomize seed", value=True)
        with gr.Row(visible=False):
            width = gr.Slider(
                label="Width",
                minimum=256,
                maximum=MAX_IMAGE_SIZE,
                step=32,
                value=1024,
            )
            height = gr.Slider(
                label="Height",
                minimum=256,
                maximum=MAX_IMAGE_SIZE,
                step=32,
                value=1024,
            )
        with gr.Row():
            guidance_scale = gr.Slider(
                label="Guidance scale",
                minimum=1,
                maximum=20,
                step=0.1,
                value=4.5,
            )
            num_inference_steps = gr.Slider(
                label="Number of inference steps",
                minimum=10,
                maximum=100,
                step=1,
                value=20,
            )

    gr.Examples(
        examples=examples,
        inputs=prompt,
        outputs=[result, seed],
        fn=generate,
        cache_examples=CACHE_EXAMPLES,
    )

    use_negative_prompt.change(
        fn=lambda x: gr.update(visible=x),
        inputs=use_negative_prompt,
        outputs=negative_prompt,
        api_name=False,
    )

    gr.on(
        triggers=[
            prompt.submit,
            negative_prompt.submit,
            run_button.click,
        ],
        fn=generate,
        inputs=[
            prompt,
            batch,
            negative_prompt,
            style_selection,
            use_negative_prompt,
            seed,
            width,
            height,
            guidance_scale,
            num_inference_steps,
            randomize_seed,
        ],
        outputs=[result, seed],
        api_name="run",
    )

if __name__ == "__main__":
    demo.queue(max_size=20).launch(share = True)
