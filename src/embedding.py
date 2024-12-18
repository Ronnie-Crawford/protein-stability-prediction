# Standard modules
import os
import itertools
import pickle
from pathlib import Path

# Third party modules
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
import esm
from transformers import AutoModel, AutoTokenizer
from transformers import EsmForProteinFolding, EsmTokenizer

# Local modules
from config_loader import config
from preprocessing import pad_variable_length_sequences
from datasets import ProteinDataset
from helpers import manage_memory, concatenate_embeddings, normalise_embeddings, fit_principal_components

def load_embeddings(
    all_dataset_names: list,
    all_datasets: list,
    batch_size: int,
    model_selections: list,
    embedding_layers: list,
    embedding_types: list,
    device: str,
    package_folder: Path
) -> tuple[list, int]:
    
    embedding_size = 0
    embeddings = []

    embedding_combinations = list(itertools.product(model_selections, embedding_layers, embedding_types))
    merged_embeddings_df = pd.DataFrame()

    for dataset_name, dataset in zip(all_dataset_names, all_datasets):

        embeddings_list = []

        for model_selection, embedding_layer, embedding_type in embedding_combinations:

            embedding_df = pd.DataFrame()
            
            embedding_sorted_path = package_folder / f"embeddings/dataset[{dataset_name}]" / f"model[{model_selection}]" / f"layer[{embedding_layer}]" / f"embedding_type[{embedding_type}]"
            embedding_tensor_path = embedding_sorted_path / "embeddings_tensor.pt"

            if not os.path.exists(embedding_tensor_path):

                if "AMPLIFY" in model_selection:

                    model, embedding_size, tokeniser = setup_amplify(device, model_selection)
                    embeddings = fetch_amplify_embeddings_batched(dataset, model, tokeniser, batch_size, device, embedding_type, embedding_layer, embedding_size)
                    if not os.path.exists(path): os.makedirs(path)
                    torch.save(embeddings, embedding_tensor_path)

                elif "ESMFold" in model_selection:
                    
                    model = EsmForProteinFolding.from_pretrained("./models/upstream_models/esmfold_3B_v1", output_hidden_states = True)
                    tokeniser = EsmTokenizer.from_pretrained("./models/upstream_models/esmfold_3B_v1")
                    embeddings = fetch_amplify_embeddings_batched(dataset, model, tokeniser, batch_size, device, embedding_type, embedding_layer, embedding_size)
                    if not os.path.exists(path): os.makedirs(path)
                    torch.save(embeddings, embedding_tensor_path)

                elif "ESM" in model_selection:

                    model, alphabet, batch_converter, embedding_size, n_layers = setup_esm(device, model_selection, package_folder)
                    embeddings = fetch_esm_embeddings_batched(dataset, model, alphabet, batch_converter, n_layers, device, batch_size, embedding_layer, embedding_type)
                    if not os.path.exists(embedding_sorted_path): os.makedirs(embedding_sorted_path)
                    torch.save(embeddings, embedding_tensor_path)

            else:

                embeddings = torch.load(embedding_tensor_path, weights_only = False, map_location = "cpu")

            embeddings_list.append(embeddings)

        if config["NORMALISE_EMBEDDINGS"]:

            embeddings_list = normalise_embeddings(embeddings_list)

        dataset.sequence_representations = concatenate_embeddings(embeddings_list)

    embedding_size = len(all_datasets[0].__dict__["sequence_representations"][0])

    return all_datasets, embedding_size

def setup_amplify(device: str, model_selection: list):

    print("Setting up amplify")

    model, tokeniser = None, None

    match model_selection:

        case "AMPLIFY_120M":

            model = AutoModel.from_pretrained("chandar-lab/AMPLIFY_120M", trust_remote_code=True)
            tokeniser = AutoTokenizer.from_pretrained("chandar-lab/AMPLIFY_120M", trust_remote_code=True)

        case "AMPLIFY_120M_base":

            model = AutoModel.from_pretrained("chandar-lab/AMPLIFY_120M_base", trust_remote_code=True)
            tokeniser = AutoTokenizer.from_pretrained("chandar-lab/AMPLIFY_120M_base", trust_remote_code=True)

        case "AMPLIFY_350M":

            model = AutoModel.from_pretrained("chandar-lab/AMPLIFY_350M", trust_remote_code=True)
            tokeniser = AutoTokenizer.from_pretrained("chandar-lab/AMPLIFY_350M", trust_remote_code=True)

        case "AMPLIFY_350M_base":

            model = AutoModel.from_pretrained("chandar-lab/AMPLIFY_350M_base", trust_remote_code=True)
            tokeniser = AutoTokenizer.from_pretrained("chandar-lab/AMPLIFY_350M_base", trust_remote_code=True)

    model.eval()
    model.to(device)
    embedding_size = 960

    return model, embedding_size, tokeniser

def setup_esm(device: str, model_selection: list, package_folder):

    model, alphabet = None, None
    upstream_models_path = package_folder / "models/upstream_models"

    match model_selection:

        case "ESM2_T6_8M_UR50D":

            #model, alphabet = esm.pretrained.esm2_t6_8M_UR50D()
            model, alphabet = load_esm2_model(upstream_models_path / "esm2_t6_8M_UR50D.pt")

        case "ESM2_T12_35M_UR50D":

            #model, alphabet = esm.pretrained.esm2_t12_35M_UR50D()
            model, alphabet = load_esm2_model(upstream_models_path / "esm2_t12_35M_UR50D.pt")
            

        case "ESM2_T30_150M_UR50D":

            #model, alphabet = esm.pretrained.esm2_t30_150M_UR50D()
            model, alphabet = load_esm2_model(upstream_models_path / "esm2_t30_150M_UR50D.pt")
            
        case "ESM2_T33_650M_UR50D":

            #model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
            model, alphabet = load_esm2_model(upstream_models_path / "esm2_t33_650M_UR50D.pt")

        case "ESM2_T36_3B_UR50D":

            #model, alphabet = esm.pretrained.esm2_t36_3B_UR50D()
            model, alphabet = load_esm2_model(upstream_models_path / "esm2_t36_3B_UR50D.pt")


        case "ESM2_T48_15B_UR50D":

            #model, alphabet = esm.pretrained.esm2_t48_15B_UR50D()
            model, alphabet = load_esm2_model(upstream_models_path / "esm2_t48_15B_UR50D.pt")
        
        case "ESMFold":
            
            model = EsmForProteinFolding.from_pretrained("facebook/esmfold_v1", output_hidden_states = True)

    batch_converter = alphabet.get_batch_converter()
    model = model.to(device)
    model.eval()
    embedding_size = model.embed_dim
    n_layers = len(model.layers)

    return model, alphabet, batch_converter, embedding_size, n_layers

def load_esm2_model(model_path: str):
    
    model_data = torch.load(model_path, map_location = "cpu")
    model_name = model_path.stem
    
    model, alphabet = esm.pretrained.load_model_and_alphabet_core(model_name, model_data)
    
    return model, alphabet

def load_esmfold_model(model_path: str):
    
    model_path = Path(model_path)
    model_data = torch.load(str(model_path), map_location = "cpu")
    cfg = model_data["cfg"]["model"]
    model_state = model_data["model"]
    model = ESMFold(esmfold_config = cfg)
    
    expected_keys = set(model.state_dict().keys())
    found_keys = set(model_state.keys())
    
    missing_essential_keys = []
    
    for missing_key in expected_keys - found_keys:
         
        if not missing_key.startswith("esm."):
             
            missing_essential_keys.append(missing_key)

    if missing_essential_keys:
        
        raise RuntimeError(f"Keys '{', '.join(missing_essential_keys)}' are missing.")

    model.load_state_dict(model_state, strict = False)
    alphabet = model.alphabet
    
    return model, alphabet

def fetch_amplify_embeddings_batched(
    dataset: Dataset,
    model,
    tokeniser,
    batch_size: int,
    device: str,
    embedding_type: str,
    embedding_layer: int,
    embedding_size: int
) -> torch.tensor:

    print("Fetching amplify embeddings in batches")

    pooled_batch_embeddings = []
    full_embeddings = [None] * len(dataset)
    dataloader = DataLoader(dataset, batch_size = batch_size, shuffle = False)

    with torch.no_grad():

        for batch_idx, batch in enumerate(dataloader):

            sequences = batch["variant_aa_seq"]
            
            inputs = tokeniser(sequences, padding = True, truncation = True, return_tensors = "pt", max_length=1024)
            inputs = inputs["input_ids"].to(device)
            model = model.to(device)
            output = model(inputs)
            batch_embeddings = output.hidden_states[embedding_layer]

            if embedding_type == "MEAN":

                pooled_batch_embeddings = batch_embeddings.mean(dim = 1).float().to(device)

            elif embedding_type == "MAX":

                pooled_batch_embeddings = batch_embeddings.max(dim = 1).values

            elif embedding_type == "MIN":

                pooled_batch_embeddings = batch_embeddings.min(dim = 1).values

            elif embedding_type == "STD":

                pooled_batch_embeddings = batch_embeddings.std(dim = 1).float().to(device)

            elif embedding_type == "PC1":

                pooled_batch_embeddings = fit_principal_components(batch_embeddings, 1, device)

            elif embedding_type == "PC2":

                pooled_batch_embeddings = fit_principal_components(batch_embeddings, 2, device)

            elif embedding_type == "PC3":

                pooled_batch_embeddings = fit_principal_components(batch_embeddings, 3, device)

            else:

                raise Exception("Invalid embedding type.")

            for i in range(len(sequences)):

                full_embeddings[batch_idx * batch_size + i] = pooled_batch_embeddings[i]

            print(f"Fetched batch {batch_idx + 1} out of {len(dataloader)}")

    print("Fetching embeddings complete!")

    return full_embeddings

def fetch_esm_embeddings_batched(
    dataset: Dataset,
    model,
    alphabet,
    batch_converter,
    n_layers: int,
    device: str,
    batch_size: int,
    embedding_layer: int,
    embedding_type: str
) -> torch.tensor:

    """
    Fetch ESM representations in batches, usually the most efficient method.
    Recommended for all but the smallest datasets.
    """

    pooled_batch_embeddings = []
    full_embeddings = [None] * len(dataset)
    dataloader = DataLoader(dataset, batch_size = batch_size, shuffle = False)
    embedding_layer = n_layers + 1 + embedding_layer

    with torch.no_grad():

        for batch_idx, batch in enumerate(dataloader):

            batch_tuples = list(zip(batch["domain_name"], batch["variant_aa_seq"]))
            batch_labels, batch_strs, batch_tokens = batch_converter(batch_tuples)
            batch_tokens = batch_tokens.to(device)
            output = model(batch_tokens, repr_layers = [embedding_layer], return_contacts = False)
            batch_embeddings = output["representations"][embedding_layer]

            if embedding_type == "RAW":
                
                pooled_batch_embeddings = []
                
                for seq_idx, seq in enumerate(batch["variant_aa_seq"]):
                    
                    seq_len = len(seq)
                    seq_embeddings = batch_embeddings[seq_idx, 1:seq_len + 1, :].cpu()
                    pooled_batch_embeddings.append(seq_embeddings)
            
            elif embedding_type == "PADDED":
                
                sequence_embeddings = []
                sequence_lengths = []
                
                for seq_idx, seq in enumerate(batch["variant_aa_seq"]):
                    
                    seq_len = len(seq)
                    seq_embeddings = batch_embeddings[seq_idx, 1:seq_len + 1, :].cpu()
                    sequence_embeddings.append(seq_embeddings)
                    sequence_lengths.append(seq_len)

                pooled_batch_embeddings = torch.nn.utils.rnn.pad_sequence(
                    sequence_embeddings, batch_first=True
                )

            elif embedding_type == "MEAN":

                pooled_batch_embeddings = batch_embeddings.mean(dim = 1).float().to(device)

            elif embedding_type == "MAX":

                pooled_batch_embeddings = batch_embeddings.max(dim = 1).values

            elif embedding_type == "MIN":

                pooled_batch_embeddings = batch_embeddings.min(dim = 1).values

            elif embedding_type == "STD":

                pooled_batch_embeddings = batch_embeddings.std(dim = 1).float().to(device)

            elif embedding_type == "PC1":

                pooled_batch_embeddings = fit_principal_components(batch_embeddings, 1, device)

            elif embedding_type == "PC2":

                pooled_batch_embeddings = fit_principal_components(batch_embeddings, 2, device)

            elif embedding_type == "PC3":

                pooled_batch_embeddings = fit_principal_components(batch_embeddings, 3, device)

            else:

                raise Exception("Invalid embedding type.")

            for i in range(len(batch["variant_aa_seq"])):

                full_embeddings[batch_idx * batch_size + i] = pooled_batch_embeddings[i]

            print(f"Fetched ESM representations for batch {batch_idx + 1} of {len(dataloader)}")

    print(f"Completed fetching ESM representations for all {len(dataset)} items")

    return full_embeddings
