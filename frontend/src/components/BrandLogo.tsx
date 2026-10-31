import type { ImgHTMLAttributes } from 'react'

type BrandLogoVariant = 'light' | 'dark' | 'monochrome'
type BrandLogoSize = 'sidebar' | 'hero'

type BrandLogoProps = Omit<ImgHTMLAttributes<HTMLImageElement>, 'src' | 'alt'> & {
  variant?: BrandLogoVariant
  size?: BrandLogoSize
  alt?: string
}

const logoAssets: Record<BrandLogoVariant, string> = {
  light: '/assets/biznexa-logo-light.png',
  dark: '/assets/biznexa-logo-dark.png',
  monochrome: '/assets/biznexa-logo-monochrome.png',
}

export function BrandLogo({
  variant = 'dark',
  size = 'sidebar',
  className = '',
  alt = 'BizNexa — See Beyond Data. Lead with Insight.',
  ...imageProps
}: BrandLogoProps) {
  return (
    <img
      {...imageProps}
      className={`brand-logo brand-logo-${size} ${className}`.trim()}
      src={logoAssets[variant]}
      alt={alt}
    />
  )
}

type BrandIconProps = Omit<ImgHTMLAttributes<HTMLImageElement>, 'src' | 'alt'> & {
  variant?: 'light' | 'dark'
  size?: 'sidebar' | 'header'
  alt?: string
}

export function BrandIcon({
  variant = 'dark',
  size = 'sidebar',
  className = '',
  alt = 'BizNexa',
  ...imageProps
}: BrandIconProps) {
  return (
    <img
      {...imageProps}
      className={`brand-icon brand-icon-${size} ${className}`.trim()}
      src={`/assets/biznexa-icon-${variant}-crop.png`}
      alt={alt}
    />
  )
}
