export interface DockerConfig {
  Labels: {
    'io.buildpacks.build.metadata': string;
    [key: string]: string;
  };
  [key: string]: unknown;
}

export interface ExtraAttrs {
  config: DockerConfig;
  [key: string]: unknown;
}

export interface ImageArtifactTag {
  name: string;
  [key: string]: unknown;
}

export interface ImageArtifact {
  digest: string;
  extra_attrs: ExtraAttrs;
  tags: ImageArtifactTag[];
  [key: string]: unknown;
}

export interface Process {
  type: string;
  command: string;
  args: string[];
  direct: boolean;
  buildpackID: string;
}

export interface BuildPackMetadata {
  processes: Process[];
  [key: string]: unknown;
}
