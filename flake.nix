{
  description = "Syng - A tool to sync data between directories and git repositories";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          gitpython
        ]);
      in
      {
        packages = {
          default = self.packages.${system}.syng;
          
          syng = pkgs.stdenv.mkDerivation {
            pname = "syng";
            version = "0.1.0";
            src = ./.;
            
            buildInputs = [
              pythonEnv
              pkgs.git
            ];
            
            installPhase = ''
              mkdir -p $out/bin
              mkdir -p $out/lib/syng
              
              cp syng.py $out/lib/syng/
              
              cat > $out/bin/syng << EOF
              #!/bin/sh
              exec ${pythonEnv}/bin/python3 $out/lib/syng/syng.py "\$@"
              EOF
              
              chmod +x $out/bin/syng
            '';
            
            meta = with pkgs.lib; {
              description = "A tool to sync data between directories and git repositories";
              homepage = "https://github.com/willyrgf/syng";
              license = licenses.mit;
              platforms = platforms.all;
            };
          };
        };
        
        apps = {
          default = self.apps.${system}.syng;
          
          syng = {
            type = "app";
            program = "${self.packages.${system}.syng}/bin/syng";
          };
        };
        
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.git
          ];
        };
      }
    );
} 