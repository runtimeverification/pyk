{
  description = "Application packaged using poetry2nix";

  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs";
  inputs.poetry2nix.url = "github:nix-community/poetry2nix/master";

  outputs = { self, nixpkgs, flake-utils, poetry2nix }:
    {
      # Nixpkgs overlay providing the application
      overlay = final: prev:
        let
          mkPyk = python:
            prev.poetry2nix.mkPoetryApplication {
              python = python;
              projectDir = ./.;
              groups = [ ];
              # We remove `"dev"` from `checkGroups`, so that poetry2nix does not try to resolve dev dependencies.
              checkGroups = [ ];
              overrides = prev.poetry2nix.overrides.withDefaults
                (finalPython: prevPython: {
                  graphql-server = prevPython.graphql-server.overridePythonAttrs
                    (oldAttrs: {
                      buildInputs = (oldAttrs.buildInputs or [ ])
                        ++ [ prevPython.setuptools ];
                    });
                  nanoid = prevPython.nanoid.overridePythonAttrs
                    (oldAttrs: {
                      buildInputs = (oldAttrs.buildInputs or [ ])
                        ++ [ prevPython.setuptools ];
                    });
                  packaging = prevPython.packaging.overridePythonAttrs
                    (oldAttrs: {
                      buildInputs = (oldAttrs.buildInputs or [ ])
                        ++ [ prevPython.flit-core ];
                    });
                });
            };
        in {
          pyk = mkPyk prev.python39;
          python310Packages.pyk = mkPyk prev.python310;
        };
    } // (flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ poetry2nix.overlay self.overlay ];
        };
      in {
        packages = {
          inherit (pkgs) pyk;
          pyk-python310 = pkgs.python310Packages.pyk;
          default = pkgs.pyk;
        };
      }));
}
