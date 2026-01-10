import React, { useCallback, useRef } from "react";
import { X, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Attachment } from "@/lib/api-client";

interface ImageUploadProps {
  images: Attachment[];
  setImages: React.Dispatch<React.SetStateAction<Attachment[]>>;
  className?: string;
  disabled?: boolean;
}

export function ImageUpload({ images, setImages, className, disabled }: ImageUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const imageFiles = Array.from(files).filter((file) => file.type.startsWith("image/"));
      if (imageFiles.length === 0) return;

      const promises = imageFiles.map((file) => {
        return new Promise<Attachment>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            const result = e.target?.result as string;
            resolve({ uri: result, name: file.name, content_type: file.type });
          };
          reader.readAsDataURL(file);
        });
      });

      try {
        const newAttachments = await Promise.all(promises);
        setImages((prev) => [...prev, ...newAttachments]);
      } catch (error) {
        console.error("Failed to read images:", error);
      }
    },
    [setImages]
  );

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const onPaste = (e: React.ClipboardEvent) => {
    if (disabled) return;
    if (e.clipboardData.files && e.clipboardData.files.length > 0) {
      handleFiles(e.clipboardData.files);
    }
  };

  const removeImage = (index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div
      className={cn("space-y-2", className)}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onPaste={onPaste}
    >
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((image, index) => (
            <div
              key={index}
              className="group relative h-20 w-20 overflow-hidden rounded-lg border border-border bg-muted"
            >
              <img
                src={image.uri}
                alt={image.name}
                className="h-full w-full object-cover transition-transform group-hover:scale-110"
              />
              <button
                type="button"
                onClick={() => removeImage(index)}
                className="absolute right-1 top-1 rounded-full bg-background/80 p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <input
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          ref={fileInputRef}
          onChange={(e) => {
            if (e.target.files) {
              handleFiles(e.target.files);
              e.target.value = "";
            }
          }}
          disabled={disabled}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 gap-2 border-dashed text-xs text-muted-foreground hover:text-foreground"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
        >
          <ImageIcon size={14} />
          <span>Add images</span>
        </Button>
        <p className="text-[10px] text-muted-foreground">
          Drag & drop or paste images directly
        </p>
      </div>
    </div>
  );
}
