import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

@Injectable()
export class PrismaService implements OnModuleInit, OnModuleDestroy {
  private prisma: PrismaClient;

  constructor() {
    this.prisma = new PrismaClient({
      log: ['query', 'info', 'warn', 'error'], 
    });
  }

  async onModuleInit() {
    await this.prisma.$connect();
    console.log('🟢 Prisma connected');
  }

  async onModuleDestroy() {
    await this.prisma.$disconnect();
    console.log('🔴 Prisma disconnected');
  }

  get client() {
    return this.prisma;
  }
}
