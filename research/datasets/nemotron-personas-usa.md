# nvidia/Nemotron-Personas-USA

- License: CC BY 4.0 (attribute NVIDIA)
- Size: 1M rows, 23 fields
- Used fields: occupation, hobbies, skills, professional_persona, education_level, uuid
- Dropped (SOP: no targeting on protected traits): sex, age, marital_status, zipcode, city/state as targeting keys
- Script: `training/prepare_nemotron.py` → 8 personas per niche pack
