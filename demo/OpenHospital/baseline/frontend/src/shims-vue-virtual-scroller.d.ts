declare module 'vue-virtual-scroller' {
  import { DefineComponent } from 'vue'

  export const RecycleScroller: DefineComponent<{
    items: any[]
    itemSize?: number | null
    keyField?: string
    direction?: 'vertical' | 'horizontal'
    buffer?: number
    pageMode?: boolean
    prerender?: number
    emitUpdate?: boolean
  }>

  export const DynamicScroller: DefineComponent<{
    items: any[]
    keyField?: string
    direction?: 'vertical' | 'horizontal'
    buffer?: number
    pageMode?: boolean
    prerender?: number
    emitUpdate?: boolean
    minItemSize?: number
  }>

  export const DynamicScrollerItem: DefineComponent<{
    item: any
    active?: boolean
    sizeDependencies?: any[]
    watchData?: boolean
    tag?: string
    emitResize?: boolean
  }>
}
