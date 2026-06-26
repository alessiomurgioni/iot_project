from werkzeug.security import generate_password_hash

if __name__ == "__main__":

    secret = input("Secret to hash (device token or owner key): ")
    if not secret:
        raise Exception("Secret not provided")

    h = generate_password_hash(secret, method="pbkdf2:sha256")
    print("\n\n##### GENERATED TOKEN HASH #####")
    print(f"Key Derivation Function: pbkdf2")
    print(f"Hashing Algorithm: sha256")
    print(f"hashed password: {h}")
